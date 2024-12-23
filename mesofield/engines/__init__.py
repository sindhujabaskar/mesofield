import pymmcore_plus
from pymmcore_plus.metadata import SummaryMetaV1
import useq
import time
from itertools import product

from typing import TYPE_CHECKING

from typing import TYPE_CHECKING, Iterable, Mapping, Sequence
if TYPE_CHECKING:
    from pymmcore_plus.core._sequencing import SequencedEvent
    from pymmcore_plus.mda.metadata import FrameMetaV1 # type: ignore
    from numpy.typing import NDArray
    from useq import MDAEvent
    PImagePayload = tuple[NDArray, MDAEvent, FrameMetaV1]  
    
from pymmcore_plus.mda import MDAEngine
    
from .enginedev import DevEngine
from .pupilengine import PupilEngine
from .mesoengine import MesoEngine

import logging
logging.basicConfig(filename='engine.log', level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')