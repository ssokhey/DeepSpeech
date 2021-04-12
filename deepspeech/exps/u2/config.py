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

from yacs.config import CfgNode

from deepspeech.models.u2 import U2Model
from deepspeech.exps.u2.model import U2Trainer
from deepspeech.exps.u2.model import U2Tester

_C = CfgNode()

_C.data = CfgNode()
ManifestDataset.params(_C.data)

_C.model = CfgNode()
U2Model.params(_C.model)

_C.training = CfgNode()
U2Trainer.params(_C.training)

_C.decoding = CfgNode()
U2Tester.params(_C.training)


def get_cfg_defaults():
    """Get a yacs CfgNode object with default values for my_project."""
    # Return a clone so that the defaults will not be altered
    # This is for the "local variable" use pattern
    return _C.clone()