import pytest
#pytest.skip("Skipping hardware-dependent MDA tests", allow_module_level=True)

from pymmcore_plus import CMMCorePlus
import useq
        

def test_mmcore_mda():
    import time
    
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    
    core.startContinuousSequenceAcquisition()
    time.sleep(1)
    img, get_metadata = core.getLastImageAndMD()
    time.sleep(1)
    img, pop_metadata = core.popNextImageAndMD()
    core.stopSequenceAcquisition()
    
    print(f"getLastImageAndMD Metadata object: {get_metadata}")
    print(F"popNextImageAndMD Metadata object: {pop_metadata}")


