import warnings
from dask.array import PerformanceWarning
from importlib import metadata

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PerformanceWarning)

try:
    __version__ = metadata.version('scarf-toolkit')
except ImportError:
    print("Scarf is not installed", flush=True)

from .datastore import *
from .readers import *
from .writers import *
from .meld_assay import *
from .utils import *
