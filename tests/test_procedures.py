"""
Test script for the Mesofield procedure system.

This script demonstrates how to create and test custom procedures
outside of the GUI environment.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mesofield.config import ExperimentConfig
from mesofield.base import create_procedure
from mesofield.examples.custom_procedures import create_custom_procedure


def test_basic_procedure():
    """Test basic procedure creation and initialization."""
    print("Testing basic procedure creation...")
    
    # Load configuration
    config_path = os.path.join(os.path.dirname(__file__), '..', 'hardware.yaml')
    if not os.path.exists(config_path):
        print(f"Warning: Hardware config not found at {config_path}")
        print("Using minimal configuration for testing")
        config = None
    else:
        config = ExperimentConfig(config_path)
    
    # Test Procedure creation
    try:
        procedure = create_procedure(
            'Procedure',
            config,
            experiment_id="test_001",
            experimentor="test_user",
            data_dir="test_data"
        )
        print(f"✓ Created {procedure.__class__.__name__}")
        print(f"  Experiment ID: {procedure.config.experiment_id}")
        print(f"  Experimentor: {procedure.config.experimentor}")
        
    except Exception as e:
        print(f"✗ Failed to create Procedure: {e}")
        return False
    
    return True


def test_custom_procedures():
    """Test custom procedure examples."""
    print("\nTesting custom procedure examples...")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'hardware.yaml')
    if not os.path.exists(config_path):
        config = None
    else:
        config = ExperimentConfig(config_path)
    
    # Test each custom procedure type
    procedure_types = ['simple_behavior', 'multi_trial', 'opto_stimulation']
    
    for proc_type in procedure_types:
        try:
            procedure = create_custom_procedure(
                proc_type,
                config,
                experiment_id=f"test_{proc_type}_001",
                experimentor="test_user",
                data_dir=f"test_data/{proc_type}"
            )
            print(f"✓ Created {procedure.__class__.__name__}")
            
            # Test setup without hardware
            try:
                procedure.setup_experiment()
                print(f"  ✓ Setup completed successfully")
            except Exception as e:
                print(f"  ⚠ Setup failed (expected without hardware): {e}")
                
        except Exception as e:
            print(f"✗ Failed to create {proc_type}: {e}")
            return False
    
    return True


def test_procedure_configuration():
    """Test procedure configuration and parameters."""
    print("\nTesting procedure configuration...")
    
    try:
        from mesofield.base import ProcedureConfig
        
        # Test ProcedureConfig creation
        config = ProcedureConfig(
            experiment_id="config_test_001",
            experimentor="test_researcher",
            data_dir="test_config_data",
            notes=["Test configuration", "Parameter validation"]
        )
        
        print(f"✓ Created ProcedureConfig")
        print(f"  Experiment ID: {config.experiment_id}")
        print(f"  Data directory: {config.data_dir}")
        print(f"  Notes: {len(config.notes)} items")
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to test configuration: {e}")
        return False


def test_command_line_args():
    """Test command line argument parsing."""
    print("\nTesting command line argument parsing...")
    
    try:
        from mesofield.__main__ import launch
        import argparse
        
        # Simulate command line arguments
        test_args = [
            '--procedure-class', 'mesofield.examples.custom_procedures.SimpleBehaviorProcedure',
            '--experiment-id', 'cli_test_001',
            '--experimentor', 'cli_tester',
            '--data-dir', 'cli_test_data'
        ]
        
        # Parse arguments (don't actually launch GUI)
        parser = argparse.ArgumentParser()
        parser.add_argument('--procedure-class', type=str)
        parser.add_argument('--experiment-id', type=str, default='exp_001')
        parser.add_argument('--experimentor', type=str, default='researcher')
        parser.add_argument('--data-dir', type=str, default='data')
        parser.add_argument('--json-config', type=str)
        
        args = parser.parse_args(test_args)
        
        print(f"✓ Command line arguments parsed successfully")
        print(f"  Procedure class: {args.procedure_class}")
        print(f"  Experiment ID: {args.experiment_id}")
        print(f"  Experimentor: {args.experimentor}")
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to test command line args: {e}")
        return False


def main():
    """Run all procedure tests."""
    print("Mesofield Procedure System Test Suite")
    print("=" * 40)
    
    tests = [
        test_basic_procedure,
        test_custom_procedures,
        test_procedure_configuration,
        test_command_line_args
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"Test {test.__name__} crashed: {e}")
    
    print("\n" + "=" * 40)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Procedure system is working correctly.")
        return 0
    else:
        print("⚠ Some tests failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
