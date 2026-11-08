# Experimental Lead/Rhythm Backend

`scripts/split_lead_rhythm.py` is an optional CPU-only second stage for a
full-length 44.1 kHz stereo aggregate-guitar stem. It predicts `lead`; its
`rhythm` output is the mixture-consistent residual `aggregate guitar - lead`.
Roles can bleed, so neither output is exact semantic ground truth.

## Rights gate

No checkpoint is bundled or downloaded. The helper accepts only the listra92
checkpoint with SHA-256:

```text
b3c47bca33609ca1ba0bb2d2076410bfd1eb941b051b72afc1f3e24d12b17eef
```

The community archive is not an original-author model card. Original training
provenance, data rights, commercial-use permission, and redistribution terms
remain unverified. `--experimental` acknowledges quality limitations; it does
not establish rights.

Inference requires a reviewed JSON rights record containing `schema_version: 1`,
the checkpoint hash above, config SHA-256
`8a27209d94bbadc4b83e0124b7689872684664fed7c3fd89780443610985f79d`,
nonempty `rights_holder`, `license_name`, `terms_source`, `permitted_use`, and
`reviewed_by` strings, and literal `true` values for `covers_model_weights`,
`covers_config`, and `intended_use_permitted`. Do not fabricate this record.
Keep it private: the generated report includes only its schema and SHA-256,
not the grant text, reviewer, or permission-document path.

## Install and run

Use Python 3.11 in an isolated environment. Replace `<skill-dir>` with the folder
containing `SKILL.md`; these commands do not assume that it is the current directory:

```powershell
python -m pip install -r "<skill-dir>/scripts/requirements-lead-rhythm.txt"
python "<skill-dir>/scripts/split_lead_rhythm.py" `
  "work/song/aggregate-guitar.wav" `
  --checkpoint "models/mbr_lead_rhythm_guitar_listra92.ckpt" `
  --model-license-evidence "private/reviewed-listra92-rights.json" `
  --output-dir "work/song/lead-rhythm" `
  --experimental `
  --acknowledge-role-bleed
```

Outputs are `lead-guitar.wav`, `rhythm-guitar.wav`, and
`lead-rhythm-report.json`. The helper uses PyTorch `weights_only=True`, strict
state-dict loading, transactional publication, and refuses existing outputs
without `--overwrite`. Pass a verified WAV to `build_guitar_karaoke.py` through
`--stem-file` with `--stem-kind lead-guitar` or `rhythm-guitar`.

## Attribution

The vendored inference code/config came from MIT-licensed
[Sound Razor](https://github.com/pedromtcosta/sound-razor) revision
`d59c0e0aa48993b40ac4bbc15810240a420434ea`, which attributes the architecture
to [Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training)
revision `84b1eac0887756b4f1a9d7a1ff49105939749ed2`. The MIT license and notice are
retained. No model weight is included or relicensed.
