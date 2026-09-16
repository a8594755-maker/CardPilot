# Bounded Windows checkpoint replacement recovery

Infrastructure experiment only; zero poker hands and no learned algorithm change.
The Seed3 same-dose experiment remains RUNNING but has no live owners. Its failed
static stage1 stopped at save iteration1118 with WinError5 from os.replace. The
old finally block deleted the fully serialized pending file. The intact latest
checkpoint is iteration1117, physical5314037. The extra4292 observed completed
hands are not retained model training state; additional worker tails are unknown.
Preserve every original checkpoint, metric, manifest, assignment and receipt.

Hypothesis: a bounded retry of the SAME serialized checkpoint can survive a
transient Windows rename/access conflict without another optimizer step or
serialization. Permanent failure must retain both the old destination and the
fully serialized pending candidate for explicit recovery. No permission changes,
security exclusions, force deletion of destination, or unlimited retries.

Implement an experiment-scoped I/O module, not a production-source rewrite.
Retry only Windows native error5/32/33, with exponential backoff25ms..250ms and
five-second deadline/max64attempts. Fail closed on other errors. Fully serialized
candidates survive failed replacement; incomplete serialization cleans only the
exact temporary file created by this call. The runtime wrapper must hash-check
the untouched production trainer and original I/O module, and substitute only
the atomic-save function in the main trainer process. Freeze the wrapper and
candidate before any future resumed training.

Tests: ordinary roundtrip; interrupted serialization; synthetic transient access
errors with exactly one serialization; permanent bounded failure and recoverable
pending payload; nonretryable failure; invalid retry limits; an actual Windows
CreateFileW handle without FILE_SHARE_DELETE that is subsequently released; an
actual lock that lasts beyond the retry budget. Test wrapper binding without
training, plus real production --help through the wrapper. Preserve all outputs
and exact commands. No actual inference, training, or external evaluation here.

Passing these tests does not identify the original lock holder. Windows allows
handles whose sharing mode prevents rename/delete; file access denial can have
other causes. Primary references:
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
- https://docs.python.org/3/library/os.html#os.replace

After qualification, finish this infrastructure record, then separately audit
and resume only the remaining Seed3 dose under an append-only recovery amendment.
Do not call the interrupted training failed as an algorithm, and do not rerun its
retained hands. The completed-but-uncheckpointed metric must stay in original
evidence; an explicitly derived consumed-metric resume view is a new artifact,
not silent history trimming. Preserve the full pending assignment chain.
