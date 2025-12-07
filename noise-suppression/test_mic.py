#!/usr/bin/env python3
"""
Microphone Audio Test Tool

Records and plays back your microphone to test how audio processing
(echo cancellation + noise suppression) sounds.
"""

import sys
import subprocess
import time
from pathlib import Path

def test_microphone(duration: int = 10) -> bool:
    """
    Record microphone audio and play it back.
    
    Args:
        duration: Recording duration in seconds
        
    Returns:
        True if successful
    """
    test_dir = Path("/tmp/mic-test")
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "test.wav"
    
    print("🎤 Microphone Audio Test")
    print("=======================")
    print()
    print(f"This will record your microphone for {duration} seconds")
    print("Then play it back so you can hear how it sounds")
    print()
    print("Ideal conditions:")
    print("  - Have TV or background noise playing (optional)")
    print("  - Speak naturally for ~{} seconds".format(duration))
    print("  - Listen back to hear the result")
    print()
    print("Current audio processing:")
    
    # Check what's active
    try:
        result = subprocess.run(
            ["pactl", "list", "modules"],
            capture_output=True,
            text=True,
            check=True
        )
        
        has_echo = "module-echo-cancel" in result.stdout
        has_double = result.stdout.count("module-echo-cancel") >= 2
        
        if has_double:
            print("  ✓ Echo cancellation (removes speaker feedback)")
            print("  ✓ Noise suppression (removes background noise)")
        elif has_echo:
            print("  ✓ Echo cancellation (removes speaker feedback)")
        else:
            print("  - No processing active")
        
    except Exception as e:
        print(f"  Warning: Could not check processing: {e}")
    
    print()
    input("Press Enter to start recording... ")
    
    print()
    print(f"⏺️  Recording for {duration} seconds...")
    print("   Speak now! (Or stay quiet to test noise suppression)")
    print()
    
    try:
        # Record
        subprocess.run(
            ["pactl", "record-sample", str(test_file), str(duration)],
            check=True,
            timeout=duration + 5
        )
        
        if not test_file.exists():
            print("✗ Recording failed - file not created")
            return False
        
        file_size = test_file.stat().st_size
        print()
        print(f"✓ Recording complete ({file_size / 1000:.1f} KB)")
        print()
        print("Analyzing audio quality...")
        
        # Simple analysis - just show file info
        print(f"  File: {test_file}")
        print(f"  Size: {file_size} bytes")
        
        print()
        print("Now playing back what was recorded...")
        print("(This is exactly what other players will hear from you)")
        print()
        
        # Play back
        subprocess.run(
            ["paplay", str(test_file)],
            check=True
        )
        
        print()
        print("✓ Playback complete")
        print()
        print("📊 Quality Assessment:")
        print()
        print("  ✓ If your voice is clear and loud")
        print("    → Processing is working well")
        print()
        print("  ✓ If background noise is barely audible")
        print("    → Noise suppression is effective")
        print()
        print("  ! If your voice sounds muffled")
        print("    → Try disabling noise suppression:")
        print("      python3 noise_suppression_pulseaudio.py disable")
        print()
        print(f"File saved: {test_file}")
        print(f"Replay anytime: paplay {test_file}")
        print()
        
        return True
        
    except subprocess.TimeoutExpired:
        print("✗ Recording timeout")
        return False
    except subprocess.CalledProcessError as e:
        print(f"✗ Recording failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test microphone audio with current processing"
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=10,
        help='Recording duration in seconds (default: 10)'
    )
    
    args = parser.parse_args()
    
    success = test_microphone(args.duration)
    sys.exit(0 if success else 1)
