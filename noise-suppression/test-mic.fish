#!/usr/bin/env fish
# Test microphone audio with current processing applied

set -l test_dir "/tmp/mic-test"
mkdir -p "$test_dir"

echo "🎤 Microphone Audio Test"
echo "======================="
echo ""
echo "This will record your microphone for 10 seconds"
echo "Then play it back so you can hear how it sounds"
echo ""
echo "Ideal conditions:"
echo "  - Have TV or background noise playing (optional)"
echo "  - Speak naturally for ~10 seconds"
echo "  - Listen back to hear the result"
echo ""

set -l choice (read -P "Ready? Press Enter to start recording...")

echo ""
echo "⏺️  Recording for 10 seconds..."
echo "   Speak now! (Or stay quiet to test noise suppression)"
echo ""

pactl record-sample "$test_dir/test.wav" 10

if test -f "$test_dir/test.wav"
    echo ""
    echo "✓ Recording saved to: $test_dir/test.wav"
    echo ""
    echo "Now playing back what was recorded..."
    echo "(This is what other players will hear from you)"
    echo ""
    
    paplay "$test_dir/test.wav"
    
    echo ""
    echo "✓ Playback complete"
    echo ""
    echo "Analysis:"
    echo "  ✓ If your voice is clear and loud"
    echo "  ✓ If background noise is quiet or absent"
    echo "  ✓ Then processing is working well"
    echo ""
    echo "File saved at: $test_dir/test.wav"
    echo "You can play it again with: paplay $test_dir/test.wav"
else
    echo "✗ Recording failed"
    exit 1
end
