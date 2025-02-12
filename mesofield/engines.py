import useq
import time
from itertools import product

from typing import TYPE_CHECKING, Iterable, Mapping, Sequence
if TYPE_CHECKING:
    from pymmcore_plus.core._sequencing import SequencedEvent
    from pymmcore_plus.mda.metadata import FrameMetaV1 # type: ignore
    from numpy.typing import NDArray
    from useq import MDAEvent
    PImagePayload = tuple[NDArray, MDAEvent, FrameMetaV1]  
    
from pymmcore_plus.metadata import SummaryMetaV1
from pymmcore_plus.mda import MDAEngine
import nidaqmx
from nidaqmx.constants import LineGrouping
import logging
logging.basicConfig(filename='engine.log', level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from mesofield.io import SerialWorker
    from mesofield.config import ExperimentConfig
    from pymmcore_plus import CMMCorePlus

class MesoEngine(MDAEngine):
    def __init__(self, mmc, use_hardware_sequencing: bool = True) -> None:
        super().__init__(mmc)
        self._mmc: CMMCorePlus = mmc
        self.use_hardware_sequencing = use_hardware_sequencing
        self._wheel_data = None
        # TODO: adder triggerable parameter 
        
    def set_config(self, cfg) -> None:
        self._config: ExperimentConfig = cfg
        self._encoder: SerialWorker = cfg.encoder
    
    def setup_sequence(self, sequence: useq.MDASequence) -> SummaryMetaV1 | None:
        """Perform setup required before the sequence is executed."""
        self._mmc.getPropertyObject('Arduino-Switch', 'State').loadSequence(self._config.led_pattern)
        self._mmc.getPropertyObject('Arduino-Switch', 'State').setValue(4) # seems essential to initiate serial communication
        self._mmc.getPropertyObject('Arduino-Switch', 'State').startSequence()

        logging.info(f'{self.__str__()} setup_sequence loaded LED sequence at time: {time.time()}')
        
        print('Arduino loaded')
        return super().setup_sequence(sequence)
    
    def exec_sequenced_event(self, event: 'SequencedEvent') -> Iterable['PImagePayload']:
        """Execute a sequenced (triggered) event and return the image data.

        This method is not part of the PMDAEngine protocol (it is called by
        `exec_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        
        custom override sequencerunning loop jgronemeyer24
        """
        
        # if self._encoder is not None:
        #     self._encoder.start()
        
        n_events = len(event.events)

        t0 = event.metadata.get("runner_t0") or time.perf_counter()
        event_t0_ms = (time.perf_counter() - t0) * 1000

        # Start sequence
        # Note that the overload of startSequenceAcquisition that takes a camera
        # label does NOT automatically initialize a circular buffer.  So if this call
        # is changed to accept the camera in the future, that should be kept in mind.
        self._mmc.startSequenceAcquisition(
            n_events,
            0,  # intervalMS  
            True,  # stopOnOverflow
        )
        logging.info(f'{self.__str__()} exec_sequenced_event with {n_events} events at t0 {t0}')
        self.post_sequence_started(event)

        n_channels = self._mmc.getNumberOfCameraChannels()
        count = 0
        iter_events = product(event.events, range(n_channels))
        # block until the sequence is done, popping images in the meantime
        while self._mmc.isSequenceRunning():
            if remaining := self._mmc.getRemainingImageCount():
                yield self._next_seqimg_payload(
                    *next(iter_events), remaining=remaining - 1, event_t0=event_t0_ms
                )
                count += 1
            else:
                if count == n_events:
                    logging.debug(f'{self.__str__()} stopped MDA: \n{self._mmc} with \n{count} events and \n{remaining} remaining with \n{self._mmc.getRemainingImageCount()} images in buffer')                 
                    break
                    #self._mmc.stopSequenceAcquisition() Might be source of early cutoff by not allowing engine to save the rest of image in buffer
                #time.sleep(0.001) #does not seem to optimize performance either way

        if self._mmc.isBufferOverflowed():  # pragma: no cover
            logging.debug(f'OVERFLOW {self.__str__()}; Images in buffer: {self.mmcore.getRemainingImageCount()}')
            raise MemoryError("Buffer overflowed")

        while remaining := self._mmc.getRemainingImageCount():
            logging.debug(f'{self.__str__()} Saving Remaining Images in buffer \n{self._mmc} with \n{count} events and \n{remaining} remaining with \n{self._mmc.getRemainingImageCount()} images in buffer')
            yield self._next_seqimg_payload(
                *next(iter_events), remaining=remaining - 1, event_t0=event_t0_ms
            )
            count += 1
    
    def teardown_sequence(self, sequence: useq.MDASequence) -> None:
        """Perform any teardown required after the sequence has been executed."""
        logging.info(f'{self.__str__()} teardown_sequence at time: {time.time()}')
        
        # Stop the Arduino LED Sequence
        self._mmc.getPropertyObject('Arduino-Switch', 'State').stopSequence()
        # Stop the SerialWorker collecting encoder data
        self._encoder.stop()
        # Get and store the encoder data
        self._wheel_data = self._encoder.get_data()
        self._config.save_wheel_encoder_data(self._wheel_data)
        self._config.save_configuration()
        pass
    


class PupilEngine(MDAEngine):
    def __init__(self, mmc, use_hardware_sequencing: bool = True) -> None:
        super().__init__(mmc)
        self._mmc: CMMCorePlus = mmc
        self.use_hardware_sequencing = use_hardware_sequencing
        self._wheel_data = None
        # TODO: add triggerable parameter
        
    def set_config(self, cfg: 'ExperimentConfig') -> None:
        self._config = cfg
        self._encoder = cfg.encoder
        self._nidaq = cfg.hardware.nidaq
        
    def exec_sequenced_event(self, event: 'SequencedEvent') -> Iterable['PImagePayload']:
        """Execute a sequenced (triggered) event and return the image data.

        This method is not part of the PMDAEngine protocol (it is called by
        `exec_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        
        custom override sequencerunning loop jgronemeyer24
        """
        n_events = len(event.events)

        t0 = event.metadata.get("runner_t0") or time.perf_counter()
        event_t0_ms = (time.perf_counter() - t0) * 1000
        
        if self._nidaq is not None:

            if self._nidaq.io is "DO":
                with nidaqmx.Task() as task:
                    task.do_channels.add_do_chan(lines=self._nidaq.lines, 
                                                 name_to_assign_to_lines="PupilEngine_Trigger",
                                                 line_grouping=LineGrouping.CHAN_FOR_ALL_LINES)
                    task.start()
                    task.write(True)
                    task.stop()

            elif self._nidaq.io is "DI":
                with nidaqmx.Task() as task:
                    task.di_channels.add_di_chan(lines=self._nidaq.lines, 
                                                 name_to_assign_to_lines="PupilEngine_Trigger",
                                                 line_grouping=LineGrouping.CHAN_FOR_ALL_LINES)
                    print(f"{task}: Waiting for trigger")
                    while not task.read():
                        pass

        # Start sequence
        # Note that the overload of startSequenceAcquisition that takes a camera
        # label does NOT automatically initialize a circular buffer.  So if this call
        # is changed to accept the camera in the future, that should be kept in mind.
        self._mmc.startSequenceAcquisition(
            n_events,
            0,  # intervalMS  # TODO: add support for this
            True,  # stopOnOverflow
        )
        logging.info(f'{self.__str__()} exec_sequenced_event with {n_events} events at t0 {t0}')
        self.post_sequence_started(event)

        n_channels = self._mmc.getNumberOfCameraChannels()
        count = 0
        iter_events = product(event.events, range(n_channels))
        # block until the sequence is done, popping images in the meantime
        while True:
            if self._mmc.isSequenceRunning():
                if remaining := self._mmc.getRemainingImageCount():
                    yield self._next_seqimg_payload(
                        *next(iter_events), remaining=remaining - 1, event_t0=event_t0_ms
                    )
                    count += 1
                else:
                    if count == n_events:
                        logging.debug(f'{self.__str__()} stopped MDA: \n{self._mmc} with \n{count} events and \n{remaining} remaining with \n{self._mmc.getRemainingImageCount()} images in buffer')
                        break
                        #self._mmc.stopSequenceAcquisition() 
                    time.sleep(0.001)
            else:
                break

        if self._mmc.isBufferOverflowed():  # pragma: no cover
            logging.debug(f'OVERFLOW {self.__str__()} MDA: \n{self._mmc} with \n{count} events and \n{remaining} remaining with \n{self._mmc.getRemainingImageCount()} images in buffer')
            raise MemoryError("Buffer overflowed")

        while remaining := self._mmc.getRemainingImageCount():
            logging.debug(f'{self.__str__()} Saving Remaining Images in buffer \n{self._mmc} with \n{count} events and \n{remaining} remaining with \n{self._mmc.getRemainingImageCount()} images in buffer')
            yield self._next_seqimg_payload(
                *next(iter_events), remaining=remaining - 1, event_t0=event_t0_ms
            )
            count += 1
    
    def teardown_sequence(self, sequence: useq.MDASequence) -> None:
        """Perform any teardown required after the sequence has been executed."""
        logging.info(f'{self.__str__()} teardown_sequence at time: {time.time()}')
        pass
    


class DevEngine(MDAEngine):
    
    def __init__(self, mmc, use_hardware_sequencing: bool = True) -> None:
        super().__init__(mmc)
        self._mmc = mmc
        self.use_hardware_sequencing = use_hardware_sequencing
        self._config = None
        self._encoder: SerialWorker = None
        print('DevEngine initialized')
        
    def set_config(self, cfg) -> None:
        self._config = cfg
    
    def exec_sequenced_event(self, event: 'SequencedEvent') -> Iterable['PImagePayload']:
        """Execute a sequenced (triggered) event and return the image data.

        This method is not part of the PMDAEngine protocol (it is called by
        `exec_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        
        custom override sequencerunning loop jgronemeyer24
        """
        n_events = len(event.events)

        t0 = event.metadata.get("runner_t0") or time.perf_counter()
        event_t0_ms = (time.perf_counter() - t0) * 1000
        # Start sequence
        # Note that the overload of startSequenceAcquisition that takes a camera
        # label does NOT automatically initialize a circular buffer.  So if this call
        # is changed to accept the camera in the future, that should be kept in mind.
        self._mmc.startSequenceAcquisition(
            n_events,
            0,  # intervalMS  
            True,  # stopOnOverflow
        )
        logging.info(f'{self.__str__()} exec_sequenced_event with {n_events} events at t0 {t0}')
        self.post_sequence_started(event)

        n_channels = self._mmc.getNumberOfCameraChannels()
        count = 0
        iter_events = product(event.events, range(n_channels))
        # block until the sequence is done, popping images in the meantime
        while True:
            if self._mmc.isSequenceRunning():
                if remaining := self._mmc.getRemainingImageCount():
                    yield self._next_seqimg_payload(
                        *next(iter_events), remaining=remaining - 1, event_t0=event_t0_ms
                    )
                    count += 1
                else:
                    if count == n_events:
                        logging.debug(f'{self.__str__()} stopped MDA: \n{self._mmc} with \n{count} events and \n{remaining} remaining with \n{self._mmc.getRemainingImageCount()} images in buffer')
                        self._mmc.stopSequenceAcquisition() 
                        break
                    time.sleep(0.001)
            else:
                break

        if self._mmc.isBufferOverflowed():  # pragma: no cover
            logging.debug(f'OVERFLOW {self.__str__()} MDA: \n{self._mmc} with \n{count} events and \n{remaining} remaining with \n{self._mmc.getRemainingImageCount()} images in buffer')
            raise MemoryError("Buffer overflowed")

        while remaining := self._mmc.getRemainingImageCount():
            logging.debug(f'{self.__str__()} Saving Remaining Images in buffer \n{self._mmc} with \n{count} events and \n{remaining} remaining with \n{self._mmc.getRemainingImageCount()} images in buffer')
            yield self._next_seqimg_payload(
                *next(iter_events), remaining=remaining - 1, event_t0=event_t0_ms
            )
            count += 1
    
    def teardown_sequence(self, sequence: useq.MDASequence) -> None:
        """Perform any teardown required after the sequence has been executed."""
        logging.info(f'{self.__str__()} teardown_sequence at time: {time.time()}')
        self._encoder.stop()
        # Get and store the encoder data
        self._wheel_data = self._encoder.get_data()
        self._config.save_wheel_encoder_data(self._wheel_data)
        self._config.save_configuration()
        pass