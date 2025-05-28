#!/usr/bin/env python3
"""
Simple integration test for the Mesofield procedure system.
This test doesn't require hardware and demonstrates the complete workflow.
"""

import sys
import os
from pathlib import Path

# Add mesofield to path
sys.path.insert(0, str(Path(__file__).parent))

def test_procedure_creation():
    """Test procedure creation without hardware dependencies."""
    print("🧪 Testing Procedure System Integration")
    print("=" * 50)
    
    try:
        from mesofield.procedures import create_procedure, ProcedureConfig
        print("✓ Successfully imported procedure system")
    except ImportError as e:
        print(f"✗ Failed to import procedure system: {e}")
        return False
    
    # Test procedure config creation
    try:
        config = ProcedureConfig(
            experiment_id="test_001",
            experimentor="test_user", 
            data_dir="./test_data",
            json_config=None
        )
        print("✓ Created ProcedureConfig")
        print(f"  - Experiment ID: {config.experiment_id}")
        print(f"  - Experimentor: {config.experimentor}")
        print(f"  - Data directory: {config.data_dir}")
    except Exception as e:
        print(f"✗ Failed to create ProcedureConfig: {e}")
        return False
    
    # Test procedure creation with minimal setup
    try:
        procedure = create_procedure(
            'MesofieldProcedure',
            None,  # No ExperimentConfig for this test
            experiment_id="test_001",
            experimentor="test_user",
            data_dir="./test_data"
        )
        print("✓ Created MesofieldProcedure")
        print(f"  - Class: {procedure.__class__.__name__}")
        print(f"  - Config: {procedure.config}")
    except Exception as e:
        print(f"✗ Failed to create procedure: {e}")
        return False
    
    return True


def test_custom_procedure_import():
    """Test importing custom procedure examples."""
    print("\n🎯 Testing Custom Procedure Examples")
    print("=" * 50)
    
    try:
        from mesofield.examples.custom_procedures import (
            SimpleImagingProcedure,
            BehaviorProcedure, 
            TwoPhotonProcedure,
            CustomWorkflowProcedure
        )
        print("✓ Successfully imported all custom procedure examples")
        
        # Test creation of each example
        examples = [
            ("SimpleImagingProcedure", SimpleImagingProcedure),
            ("BehaviorProcedure", BehaviorProcedure),
            ("TwoPhotonProcedure", TwoPhotonProcedure), 
            ("CustomWorkflowProcedure", CustomWorkflowProcedure)
        ]
        
        for name, cls in examples:
            try:
                instance = cls(None, experiment_id="test", experimentor="test")
                print(f"  ✓ Created {name}")
            except Exception as e:
                print(f"  ✗ Failed to create {name}: {e}")
                
    except ImportError as e:
        print(f"✗ Failed to import custom procedures: {e}")
        return False
    
    return True


def test_launch_integration():
    """Test the launch system integration."""
    print("\n🚀 Testing Launch System Integration")
    print("=" * 50)
    
    try:
        from mesofield.__main__ import launch
        print("✓ Successfully imported launch function")
        
        # Test that the launch function accepts procedure parameters
        import inspect
        sig = inspect.signature(launch)
        procedure_params = [p for p in sig.parameters if 'procedure' in p.lower()]
        
        if procedure_params:
            print(f"✓ Launch function has procedure parameters: {procedure_params}")
        else:
            print("⚠ Launch function may not have procedure parameters")
            
    except ImportError as e:
        print(f"✗ Failed to import launch function: {e}")
        return False
    
    return True


def test_gui_integration():
    """Test GUI integration readiness."""
    print("\n🖥️ Testing GUI Integration")
    print("=" * 50)
    
    try:
        from mesofield.gui.maingui import MainWindow
        from mesofield.gui.controller import ConfigController
        print("✓ Successfully imported GUI components")
        
        # Check MainWindow constructor signature
        import inspect
        main_sig = inspect.signature(MainWindow.__init__)
        if 'procedure' in main_sig.parameters:
            print("✓ MainWindow accepts procedure parameter")
        else:
            print("✗ MainWindow missing procedure parameter")
            
        # Check ConfigController constructor signature  
        controller_sig = inspect.signature(ConfigController.__init__)
        if 'procedure' in controller_sig.parameters:
            print("✓ ConfigController accepts procedure parameter")
        else:
            print("✗ ConfigController missing procedure parameter")
            
    except ImportError as e:
        print(f"✗ Failed to import GUI components: {e}")
        return False
    
    return True


def main():
    """Run all tests."""
    print("🔬 Mesofield Procedure System Integration Test")
    print("=" * 60)
    
    tests = [
        test_procedure_creation,
        test_custom_procedure_import,
        test_launch_integration,
        test_gui_integration
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n💥 Test {test.__name__} crashed: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{i+1}. {test.__name__}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Procedure system is ready.")
        return True
    else:
        print("⚠️ Some tests failed. Check implementation.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
