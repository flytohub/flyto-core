# flyto-core Demo Recording
# Generates: demo.gif
#
# Usage: cd flyto-core/src && vhs ../examples/demo_video/demo.tape

Output "../examples/demo_video/demo.gif"
Output "../examples/demo_video/demo.mp4"

Set Shell "bash"
Set FontSize 16
Set Width 1200
Set Height 700
Set Padding 20
Set Theme "Dracula"
Set TypingSpeed 30ms
Set PlaybackSpeed 1

Type "FLYTO_VALIDATION_MODE=dev python ../examples/demo_video/record.py"
Enter
Sleep 120s
