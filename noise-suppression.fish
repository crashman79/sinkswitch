#!/usr/bin/env fish
# Convenient noise suppression manager for PipeWire
# Just run: ./noise-suppression

set -l script_dir (dirname (status -f))
set -l ns_dir "$script_dir/noise-suppression"
set -l python_exe "$ns_dir/venv/bin/python3"

if not test -f "$python_exe"
    echo "❌ Virtual environment not found. Running setup..."
    cd "$ns_dir"
    ./setup.fish
    set python_exe "$ns_dir/venv/bin/python3"
end

# Check if arguments provided
if test (count $argv) -eq 0
    # No arguments - show menu
    echo "🎤 Noise Suppression Manager"
    echo "============================"
    echo ""
    echo "1. List Devices"
    echo "2. Install"
    echo "3. Start"
    echo "4. Stop"
    echo "5. Status"
    echo "6. Quick Start Guide"
    echo ""
    
    set -l choice (read -P "Choose option (1-6): ")
    
    switch $choice
        case 1
            $python_exe "$ns_dir/noise_suppression.py" list-devices
        case 2
            echo ""
            echo "First, list your devices:"
            $python_exe "$ns_dir/noise_suppression.py" list-devices
            echo ""
            set -l device (read -P "Enter device name: ")
            if test -n "$device"
                $python_exe "$ns_dir/noise_suppression.py" install --device "$device"
            end
        case 3
            $python_exe "$ns_dir/noise_suppression.py" start
        case 4
            $python_exe "$ns_dir/noise_suppression.py" stop
        case 5
            $python_exe "$ns_dir/noise_suppression.py" status
        case 6
            cat "$ns_dir/QUICK_START.md"
        case '*'
            echo "Invalid choice"
    end
else
    # Pass arguments directly to Python script
    $python_exe "$ns_dir/noise_suppression.py" $argv
end
