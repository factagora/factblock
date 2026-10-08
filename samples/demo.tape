# The README and slide demo: FactBlock in about 40 seconds, animated with `factblock demo` (Rich) over the
# real samples. Every number on screen is read from samples/cramer, samples/rates and
# bench/streamingqa/results.json at record time. Recorded with vhs (https://github.com/charmbracelet/vhs):
#   brew install vhs && vhs samples/demo.tape
# from the repository root. Outputs: samples/demo.gif, samples/demo.mp4, samples/demo-keyframe.png (scene 2).
Output samples/demo.gif
Output samples/demo.mp4
Set Shell "bash"
Set FontSize 22
Set Width 1280
Set Height 720
Set Padding 24
Set Theme "GitHub Dark"
Set TypingSpeed 22ms
Set Framerate 24

# a fresh shell: this checkout with the demo extra, a short prompt; none of it recorded
Hide
Type "uv sync -q --extra demo && export PATH=$PWD/.venv/bin:$PATH PS1='$ ' VIRTUAL_ENV_DISABLE_PROMPT=1 && factblock --help >/dev/null && clear"
Enter
Wait@120s /\$$/
Type "clear && factblock demo title"
Enter
Wait /\$$/
Show
Sleep 2.5s

Hide
Type "clear"
Enter
Show
Type "factblock demo timeline samples/cramer --as-of 2024-09-30 2025-09-30 2026-09-10"
Sleep 300ms
Enter
Wait@20s /\$$/
Sleep 2s

Hide
Type "clear"
Enter
Show
Type "factblock demo why samples/cramer f8c739a204944e7f --as-of 2026-09-10"
Sleep 300ms
Enter
Wait@20s /\$$/
Sleep 1s
Screenshot samples/demo-keyframe.png
Sleep 2s

Hide
Type "clear"
Enter
Show
Type "factblock demo replaced samples/rates c1 --as-of 2024-10-01 2024-08-01"
Sleep 300ms
Enter
Wait@20s /\$$/
Sleep 2s

Hide
Type "clear"
Enter
Show
Type "factblock demo verdict samples/cramer 66027d5985bf9605"
Sleep 300ms
Enter
Wait@20s /\$$/
Sleep 2s

Hide
Type "clear"
Enter
Show
Type "factblock demo leak bench/streamingqa/results.json"
Sleep 300ms
Enter
Wait@20s /\$$/
Sleep 2.5s

Hide
Type "clear && factblock demo end"
Enter
Wait /\$$/
Show
Sleep 3.5s
