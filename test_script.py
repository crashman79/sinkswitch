import sys
import os
import subprocess

# Add src to PYTHONPATH
sys.path.append(os.path.abspath('src'))

from audio_router_engine import AudioRouterEngine

# 1. Create Engine
engine = AudioRouterEngine(auto_mono_single_channel_bluetooth=False, force_bluetooth_mono=True)

# 2. Get Running Apps
apps = engine._get_running_applications()
print("Running Applications:", apps)

# 3. Handle target sink resolution BEFORE manual parse to use in loop condition
input_device = 'bluez_output.00_02_3C_AD_09_85.1'
effective_target = engine._get_effective_target_sink(input_device)
resolved = engine._resolve_sink(effective_target)
target_sink_id = resolved[0] if resolved else None

# 4. Manual Parse
app_name = 'PipeWire ALSA [Plex]'
to_move = []
all_sink_ids = []

result = subprocess.run(['pactl', 'list', 'sink-inputs'], capture_output=True, text=True)
current_sink_input = None
current_sink_num = None

for line in result.stdout.split('\n'):
    line_stripped = line.strip()
    if line_stripped.startswith('Sink Input #'):
        current_sink_input = line_stripped.split('#')[1].strip()
        current_sink_num = None
    elif current_sink_input and line_stripped.startswith('Sink:'):
        parts = line_stripped.split(':', 1)
        if len(parts) > 1:
            current_sink_num = parts[1].strip().split()[0] if parts[1].strip() else None
            all_sink_ids.append((current_sink_input, current_sink_num))
    elif current_sink_input and 'application.name' in line and app_name in line:
        # Same loop condition from _route_pa_stream:
        if current_sink_num is None or current_sink_num != target_sink_id:
            to_move.append((current_sink_input, current_sink_num))

print(f"Manual Parse for {app_name}:")
print(f"  to_move items: {to_move}")
print(f"  current sink ids (input_id, sink_id): {all_sink_ids}")

# 5. Print target results
print(f"Effective target: {effective_target}")
print(f"Resolved: {resolved}")

# 6. Call _route_pa_stream
ret = engine._route_pa_stream(app_name, effective_target)
print(f"Result of _route_pa_stream: {ret}")
