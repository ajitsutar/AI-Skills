Source: https://github.com/ZFTurbo/Music-Source-Separation-Training
Revision: 84b1eac0887756b4f1a9d7a1ff49105939749ed2

Copied from the MIT-licensed Sound Razor vendoring at:
https://github.com/pedromtcosta/sound-razor
Sound Razor revision: d59c0e0aa48993b40ac4bbc15810240a420434ea

Mel-Band RoFormer architecture and attention implementation, vendored under MIT.
Local changes: the attention import is relative, attention uses PyTorch's current
SDPA context manager, and the rotary embedding import narrowly filters the AMP
deprecation warning from the dependency version required by audio-separator.
Model weights are not included.

