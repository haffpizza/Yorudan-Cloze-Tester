# Yorudan Cloze Tester
Desktop app for quickly generating [cloze tests](https://en.wikipedia.org/wiki/Cloze_test) using any video of your choosing. Any video playable by [mpv](https://mpv.io/) is compatible, but only subtitles in .srt format are compatible (if your subtitles are not in .srt format, see note #3 below)
## Compatibility:
Windows and Linux builds are provided, but the Linux version is not complete yet. I also plan to provide a Mac build eventually. If you would like to use YCT on a different platform, or if the provided build is not working on your system, it is recommended that you build the executable yourself (instructions are provided below) or just run YCT.py itself.
## To start:
1) Place all files in the same folder and run YCT.exe. If you have an older computer, it might take 10 or more seconds to start.
2) Select a folder which contains video files and corresponding subtitle files. To ensure that the video and subtitle files are paired correctly, make sure that they have the same name (example: episode1.mp4 + episode1.srt). There is not a limit to the number of files that YCT can select from.
> If you have image-based subtitles in .sup format, you can also place those in the folder and they will be shown in the video player after answering a question. This is useful if you converted subtitles from image (.sup) to text (.srt) using an OCR and want to review them.
3) Select the language of the videos you loaded. YCT officially supports Japanese and English, but it could be used for any language using the Roman alphabet.

## Test:
1) Once the videos and subtitles are loaded, a subtitle will be selected at random and its corresponding video will automatically play. You can pad the start and end of clips using the arrow keys at the bottom of the window (0-5000 milliseconds).
2) Replay the clip as many times as you need by pressing SPACE. Once you are ready to answer, press ENTER and the subtitle, with one word deleted, will appear. The video cannot be replayed until you submit an answer.
3) Type in the missing part of the subtitle and press ENTER. The correct answer will appear. You can replay the clip at will again.
4) Press ENTER to move on to another clip.

## Notes:
1) Proper nouns, punctuation, and most onomatopoeia will not be selected for testing.
2) Anything contained within parentheses or brackets will not be selected and will not be shown.
3) If your subtitles are not in .srt format, you can easily convert them using [Subtitle Edit](https://github.com/SubtitleEdit/subtitleedit).
4) If you are seeing clips that are too short or too easy, you might want to try deleting them from the subtitle file. You can easily do this using Subtitle Edit.
> To quickly find the shortest subtitle lines using Subtitle Edit, go to Tools, Sort by, and then select either Duration or Text - total length.

#### excluded_strings.txt
Characters, or strings of characters, on this list will not be selected. However, the character(s) may still appear if selected as part of a larger string. For example, adding あ to the list prevents the string あ from being selected, but ああ and あふれる can still be selected.
#### excluded_chars.txt
More strict than the above list, a string of text containing any of these characters will never be selected. For example, adding あ to the list will prevent あ, ああ, and あふれる from being selected.

In both cases, subtitles containing these characters may still be selected even if not every string of characters is eligible.

## Building YCT for Windows:
1) Install the following libraries:
* PySide6
* regex
* python-mpv
* spacy + en_core_web_sm
* fugashi
* unidic-lite
2) Find the directory for unidic_lite (required for Japanese) using:
  
`python -c "import unidic_lite, pathlib; print(pathlib.Path(unidic_lite.__file__).parent)"`

3) Then, plug the path given into the following command:

`pyinstaller YCT.py --windowed --onefile --add-data "COPYPATHHERE;unidic_lite"`

5) All other libraries will be automatically included.
6) Download [libmpv-2.dll](https://sourceforge.net/projects/mpv-player-windows/files/libmpv/) and place it next to the executable. Alternatively, you can place it in PATH, but doing so will not cause it to be built into the executable.
7) Don't forget to also place the two .txt files next to the executable.
