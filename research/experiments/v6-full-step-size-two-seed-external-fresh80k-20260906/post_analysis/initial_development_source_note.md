# Initial versus executed source — evidence preservation, not a rerun

The initial experiment logger `source_manifest.json` captured the first development
runner before the explicit Python/package/thread-environment admission and exact
outer-argv recording additions. That first draft was used in the initial 70-test
offline development run, not for Slumbot requests. The other six files in the
initial seven-file manifest still match their current source files.

The initial runner was retained in the tool session and is now archived at
`initial_development_sources/run_pair.py`. Its exact bytes were verified against
the original logger manifest: 32,757 bytes, SHA256
`0a6d8e36c9ed69a7ce3c9e6f10b5c07fc89d5a4f1943ffcc692ff572402eafc8`.
No source was reconstructed by guessing and no initial manifest was overwritten.

The actual executing runner remains SHA256
`3e50a578fc6ab45d8c4447d2289de5cdfb49d6b2c134b5ee105451963e802b66`,
bound by `launch_spec.json`, `binding_qualification.json`, `input_manifest.json`
and `execution_code/source_files`. It passed the final 70-test preparation and
70-test pre-request rerun before any new Slumbot request. This final frozen source,
not the initial development manifest alone, defines the executed protocol.

This operation only preserves the missing time-specific source snapshot. It
changes no executing source, model, session evidence, experiment logger, research
decision or hand count. The controller still owns the live logger. Snapshot/note
attachment is deferred with the other post-analysis artifacts until owner exit.
