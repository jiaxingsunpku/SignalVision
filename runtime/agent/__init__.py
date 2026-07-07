from .base import BaseAgent
from .rl_agent import RLAgent

# Core algorithms used by the bundled SUMO scripts and dashboard presets.
from .maxpressure import MaxPressureAgent
from .ppo_pfrl import IPPO_pfrl
from .fixedtime import FixedTimeAgent


OPTIONAL_IMPORT_ERRORS = {}


def _optional_import(name, importer):
    try:
        importer()
    except ModuleNotFoundError as exc:
        OPTIONAL_IMPORT_ERRORS[name] = exc


_optional_import('colight', lambda: exec('from .colight import CoLightAgent', globals()))
_optional_import('colight_pytorch_agent', lambda: exec('from .colight_pytorch_agent import CoLightAgent as CoLightPytorchAgent', globals()))
_optional_import('dqn', lambda: exec('from .dqn import DQNAgent', globals()))
_optional_import('sotl', lambda: exec('from .sotl import SOTLAgent', globals()))
_optional_import('frap', lambda: exec('from .frap import FRAP_DQNAgent', globals()))
_optional_import('maddpg_v2', lambda: exec('from .maddpg_v2 import MADDPGAgent', globals()))
_optional_import('magd', lambda: exec('from .magd import MAGDAgent', globals()))
_optional_import('presslight', lambda: exec('from .presslight import PressLightAgent', globals()))
_optional_import('mplight', lambda: exec('from .mplight import MPLightAgent', globals()))
_optional_import('ppo', lambda: exec('from .ppo import PPOAgent', globals()))
