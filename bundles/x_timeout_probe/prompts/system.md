This is a harness test, not a repair task. Follow these steps exactly, one tool call per step, and do not
investigate the issue.

1. Call write_file with filepath "timeout_probe_marker.txt" and content "written before any timeout".
2. Call run_command with command "sleep 75; echo finished-long-command".
3. Call get_status.
4. Call run_command with command "sleep 20; echo tick". Repeat step 4 until you are stopped.

Never call submit_patch.
