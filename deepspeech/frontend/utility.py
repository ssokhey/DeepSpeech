# Copyright (c) 2021 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Contains data helper functions."""
import numpy as np
import math
import json
import codecs
import os
import tarfile
import time
import logging
from threading import Thread
from multiprocessing import Process, Manager, Value

from paddle.dataset.common import md5file

logger = logging.getLogger(__name__)

__all__ = [
    "load_cmvn", "read_manifest", "rms_to_db", "rms_to_dbfs", "max_dbfs",
    "mean_dbfs", "gain_db_to_ratio", "normalize_audio", "SOS", "EOS", "UNK",
    "BLANK"
]

IGNORE_ID = -1
SOS = "<sos/eos>"
EOS = SOS
UNK = "<unk>"
BLANK = "<blank>"

# """Load and parse manifest file.

# Instances with durations outside [min_duration, max_duration] will be
# filtered out.

# :param manifest_path: Manifest file to load and parse.
# :type manifest_path: str
# :param max_duration:maximum output seq length, in seconds for raw wav, in frame numbers for feature data.
# :type max_duration: float
# :param min_duration: minimum input seq length, in seconds for raw wav, in frame numbers for feature data.
# :type min_duration: float
# :return: Manifest parsing results. List of dict.
# :rtype: list
# :raises IOError: If failed to parse the manifest.
# """


def read_manifest(
        manifest_path,
        max_input_len=float('inf'),
        min_input_len=0.0,
        max_output_len=500.0,
        min_output_len=0.0,
        max_output_input_ratio=10.0,
        min_output_input_ratio=0.05, ):

    manifest = []
    for json_line in codecs.open(manifest_path, 'r', 'utf-8'):
        try:
            json_data = json.loads(json_line)
        except Exception as e:
            raise IOError("Error reading manifest: %s" % str(e))
        feat_len = json_data["feat_shape"][0]
        token_len = json_data["token_shape"][0]
        conditions = [
            feat_len > min_input_len,
            feat_len < max_input_len,
            token_len > min_output_len,
            token_len < max_output_len,
            token_len / feat_len > min_output_input_ratio,
            token_len / feat_len < max_output_input_ratio,
        ]
        if all(conditions):
            manifest.append(json_data)
    return manifest

    # parser.add_argument('--max_input_len', type=float,
    #                     default=20,
    #                     help='maximum output seq length, in seconds for raw wav, in frame numbers for feature data')
    # parser.add_argument('--min_output_len', type=float,
    #                     default=0, help='minimum input seq length, in modeling units')
    # parser.add_argument('--max_output_len', type=float,
    #                     default=500,
    #                     help='maximum output seq length, in modeling units')
    # parser.add_argument('--min_output_input_ratio', type=float, default=0.05,
    #                     help='minimum output seq length/output seq length ratio')
    # parser.add_argument('--max_output_input_ratio', type=float, default=10,
    #                     help='maximum output seq length/output seq length ratio')


def rms_to_db(rms: float):
    """Root Mean Square to dB.

    Args:
        rms ([float]): root mean square

    Returns:
        float: dB
    """
    return 20.0 * math.log10(max(1e-16, rms))


def rms_to_dbfs(rms: float):
    """Root Mean Square to dBFS.
    https://fireattack.wordpress.com/2017/02/06/replaygain-loudness-normalization-and-applications/
    Audio is mix of sine wave, so 1 amp sine wave's Full scale is 0.7071, equal to -3.0103dB.
   
    dB = dBFS + 3.0103
    dBFS = db - 3.0103
    e.g. 0 dB = -3.0103 dBFS

    Args:
        rms ([float]): root mean square

    Returns:
        float: dBFS
    """
    return rms_to_db(rms) - 3.0103


def max_dbfs(sample_data: np.ndarray):
    """Peak dBFS based on the maximum energy sample. 

    Args:
        sample_data ([np.ndarray]): float array, [-1, 1].

    Returns:
        float: dBFS 
    """
    # Peak dBFS based on the maximum energy sample. Will prevent overdrive if used for normalization.
    return rms_to_dbfs(max(abs(np.min(sample_data)), abs(np.max(sample_data))))


def mean_dbfs(sample_data):
    """Peak dBFS based on the RMS energy. 

    Args:
        sample_data ([np.ndarray]): float array, [-1, 1].

    Returns:
        float: dBFS 
    """
    return rms_to_dbfs(
        math.sqrt(np.mean(np.square(sample_data, dtype=np.float64))))


def gain_db_to_ratio(gain_db: float):
    """dB to ratio

    Args:
        gain_db (float): gain in dB

    Returns:
        float: scale in amp
    """
    return math.pow(10.0, gain_db / 20.0)


def normalize_audio(sample_data: np.ndarray, dbfs: float=-3.0103):
    """Nomalize audio to dBFS.
    
    Args:
        sample_data (np.ndarray): input wave samples, [-1, 1].
        dbfs (float, optional): target dBFS. Defaults to -3.0103.

    Returns:
        np.ndarray: normalized wave
    """
    return np.maximum(
        np.minimum(sample_data * gain_db_to_ratio(dbfs - max_dbfs(sample_data)),
                   1.0), -1.0)


def _load_json_cmvn(json_cmvn_file):
    """ Load the json format cmvn stats file and calculate cmvn

    Args:
        json_cmvn_file: cmvn stats file in json format

    Returns:
        a numpy array of [means, vars]
    """
    with open(json_cmvn_file) as f:
        cmvn_stats = json.load(f)

    means = cmvn_stats['mean_stat']
    variance = cmvn_stats['var_stat']
    count = cmvn_stats['frame_num']
    for i in range(len(means)):
        means[i] /= count
        variance[i] = variance[i] / count - means[i] * means[i]
        if variance[i] < 1.0e-20:
            variance[i] = 1.0e-20
        variance[i] = 1.0 / math.sqrt(variance[i])
    cmvn = np.array([means, variance])
    return cmvn


def _load_kaldi_cmvn(kaldi_cmvn_file):
    """ Load the kaldi format cmvn stats file and calculate cmvn

    Args:
        kaldi_cmvn_file:  kaldi text style global cmvn file, which
           is generated by:
           compute-cmvn-stats --binary=false scp:feats.scp global_cmvn

    Returns:
        a numpy array of [means, vars]
    """
    means = []
    variance = []
    with open(kaldi_cmvn_file, 'r') as fid:
        # kaldi binary file start with '\0B'
        if fid.read(2) == '\0B':
            logger.error('kaldi cmvn binary file is not supported, please '
                         'recompute it by: compute-cmvn-stats --binary=false '
                         ' scp:feats.scp global_cmvn')
            sys.exit(1)
        fid.seek(0)
        arr = fid.read().split()
        assert (arr[0] == '[')
        assert (arr[-2] == '0')
        assert (arr[-1] == ']')
        feat_dim = int((len(arr) - 2 - 2) / 2)
        for i in range(1, feat_dim + 1):
            means.append(float(arr[i]))
        count = float(arr[feat_dim + 1])
        for i in range(feat_dim + 2, 2 * feat_dim + 2):
            variance.append(float(arr[i]))

    for i in range(len(means)):
        means[i] /= count
        variance[i] = variance[i] / count - means[i] * means[i]
        if variance[i] < 1.0e-20:
            variance[i] = 1.0e-20
        variance[i] = 1.0 / math.sqrt(variance[i])
    cmvn = np.array([means, variance])
    return cmvn


def _load_npz_cmvn(npz_cmvn_file, eps=1e-20):
    npzfile = np.load(npz_cmvn_file)
    means = npzfile["mean"]
    std = npzfile["std"]
    std = np.clip(std, eps, None)
    variance = 1.0 / std
    cmvn = np.array([means, variance])
    return cmvn


def load_cmvn(cmvn_file: str, filetype: str):
    """load cmvn from file.

    Args:
        cmvn_file (str): cmvn path.
        filetype (str): file type, optional[npz, json, kaldi].

    Raises:
        ValueError: file type not support.

    Returns:
        Tuple[np.ndarray, np.ndarray]: mean, istd
    """
    assert filetype in ['npz', 'json', 'kaldi'], filetype
    filetype = filetype.lower()
    if filetype == "json":
        cmvn = _load_json_cmvn(cmvn_file)
    elif filetype == "kaldi":
        cmvn = _load_kaldi_cmvn(cmvn_file)
    elif filtype == "npz":
        cmvn = _load_npz_cmvn(cmvn_file)
    else:
        raise ValueError(f"cmvn file type no support: {filetype}")
    return cmvn[0], cmvn[1]
