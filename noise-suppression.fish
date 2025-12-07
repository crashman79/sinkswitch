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
    echo "🎤 Audio Enhancement Tools"
    echo "=========================="
    echo ""
    echo "ECHO CANCELLATION (Removes speaker feedback from mic)"
    echo "1. Enable echo cancellation"
    echo "2. Disable echo cancellation"
    echo "3. Check echo cancellation status"
    echo ""
    echo "NOISE SUPPRESSION (RNNoise - removes background noise)"
    echo "4. Install noise suppression"
    echo "5. Check noise suppression status"
    echo ""
    echo "6. Quit"
    echo ""
    
    set -l choice (read -P "Choose option (1-6): ")
    
    switch $choice
        case 1
            echo ""
            echo "Available microphones:"
            $python_exe "$ns_dir/echo_cancellation.py" list-devices
            echo ""
            set -l device (read -P "Enter device name (or press Enter for default): ")
            if test -n "$device"
                $python_exe "$ns_dir/echo_cancellation.py" enable --device "$device"
            else
                $python_exe "$ns_dir/echo_cancellation.py" enable
            end
        case 2
            $python_exe "$ns_dir/echo_cancellation.py" disable
        case 3
            $python_exe "$ns_dir/echo_cancellation.py" status
        case 4
            echo ""
            echo "Available microphones:"
            $python_exe "$ns_dir/noise_suppression.py" list-devices
            echo ""
            set -l device (read -P "Enter device name: ")
            if test -n "$device"
                $python_exe "$ns_dir/noise_suppression.py" install --device "$device"
            end
        case 5
            $python_exe "$ns_dir/noise_suppression.py" status
        case 6
            exit 0
        case '*'
            echo "Invalid choice"
    end
else
    # Pass arguments to the appropriate script based on first argument
    set -l cmd $argv[1]
    set -l rest $argv[2..-1]
    
    if string match -q "echo*" "$cmd"
        $python_exe "$ns_dir/echo_cancellation.py" $rest
    else
        $python_exe "$ns_dir/noise_suppression.py" $argv
    end
end
