#!/usr/bin/env fish
# Test audio processing by recording and playing back your microphone

set -l script_dir (dirname (status -f))
set -l test_file "/tmp/mic_test_$(date +%s).wav"

echo "🎤 Microphone Audio Processing Test"
echo "==================================="
echo ""

# Check if noise suppression is active
python3 "$script_dir/noise_suppression_pulseaudio.py" status

echo ""
echo "Recording Instructions:"
echo "====================="
echo "1. Make sure TV/background noise is present (to test noise suppression)"
echo "2. Speak naturally for 10 seconds"
echo "3. Include some silence so you can hear noise suppression in action"
echo ""

set -l duration (read -P "Recording duration in seconds (default 10): ")
if test -z "$duration"
    set duration 10
end

echo ""
echo "🔴 RECORDING in 3 seconds... Speak now!"
sleep 3

# Record from the LifeCam microphone via ALSA
echo "(Recording...)"
timeout "$duration" arecord -D hw:0,0 -f S16_LE -r 48000 "$test_file" > /dev/null 2>&1

if not test -f "$test_file"
    echo "❌ Recording failed"
    exit 1
end

set -l file_size (stat -f%z "$test_file" 2>/dev/null || stat -c%s "$test_file")
echo "✓ Recording saved: $test_file ($(math "$file_size / 1000") KB)"
echo ""

# Analyze the recording
echo "📊 Analysis:"
echo "==========="

# Calculate recording characteristics (mono: 1 channel, 16-bit = 2 bytes)
set -l expected_bytes (math "$duration * 48000 * 1 * 2")
set -l percent (math "($file_size * 100) / $expected_bytes")

if test $percent -lt 50
    echo "⚠️  Recording may be incomplete or silent"
else if test $percent -gt 110
    echo "✓ Recording looks complete"
end

echo ""
echo "Now playing back what others will hear..."
echo ""

# Play back the recording
paplay "$test_file" 2>/dev/null

echo ""
echo "Playback complete!"
echo ""
echo "📋 Observations:"
echo "==============="
echo "✓ Did your voice sound clear?"
echo "✓ Could you hear background noise (TV, fan)?"
echo "✓ Was there any echo/feedback?"
echo ""

set -l keep (read -P "Keep recording for reference? (y/n, default: delete): ")
if test "$keep" != "y"
    rm -f "$test_file"
    echo "Recording deleted"
else
    echo "Recording saved to: $test_file"
    echo "Play again with: paplay $test_file"
end

echo ""
echo "Test complete! If you heard clear voice with minimal background noise,"
echo "your audio processing is working well for SCUM."
