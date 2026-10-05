# 20 seconds of factblock, recorded with vhs (https://github.com/charmbracelet/vhs):
#   brew install vhs && vhs samples/demo.tape   -> samples/demo.gif
# Run from the repository root with `uv sync` done, so `factblock` resolves to this checkout.
Output samples/demo.gif
Set Shell "bash"
Set FontSize 15
Set Width 1100
Set Height 640
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms

Type "factblock scan samples/cramer --as-of 2025-01-01 | head -4"
Enter
Sleep 3s
Type "factblock recall samples/cramer 'Nvidia data center' --as-of 2025-01-01 --limit 3"
Enter
Sleep 3.5s
Type "factblock why samples/cramer 1b77a1a885470207 --as-of 2026-09-10"
Enter
Sleep 4s
Type "factblock why samples/cramer 1b77a1a885470207 --as-of 2025-01-01"
Enter
Sleep 3.5s
Type "factblock leak samples/rates samples/rates-questions.jsonl"
Enter
Sleep 3s
