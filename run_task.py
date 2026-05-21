import sys
from pathlib import Path
from config_parser import ConfigParser
from audio_router_engine import AudioRouterEngine

def main():
    config_path = Path.home() / ".config/sinkswitch/config/routing_rules.yaml"
    parser = ConfigParser(str(config_path))
    rules = parser.parse()
    
    engine = AudioRouterEngine(auto_mono_single_channel_bluetooth=False, force_bluetooth_mono=True)
    
    # Get current streams to find Plex
    streams = engine.device_monitor._get_audio_streams()
    plex_stream = next((s for s in streams if s.get('application_name') == 'Plex'), None)
    
    if plex_stream:
        print(f"Plex sink before apply: {plex_stream.get('sink')}")
    else:
        print("Plex stream not found")
        
    results = engine.apply_rules(rules)
    
    # Find results for "Media Apps to Bluetooth"
    media_apps_result = next((r for r in results if r.get('rule_name') == 'Media Apps to Bluetooth'), None)
    if media_apps_result:
        print(f"Media Apps to Bluetooth result row: {media_apps_result}")
    else:
        # If not exact match, look for any result
        print(f"Media Apps to Bluetooth result row: {results[0] if results else 'No results'}")

    # Get updated streams
    streams_after = engine.device_monitor._get_audio_streams()
    plex_stream_after = next((s for s in streams_after if s.get('application_name') == 'Plex'), None)
    if plex_stream_after:
        print(f"Plex sink after apply: {plex_stream_after.get('sink')}")
    else:
        print("Plex stream not found after apply")

if __name__ == "__main__":
    main()
