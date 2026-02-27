persist where the user leaves the directory structure for looking at duplicate images, so that when action is done, they don't have to navigate to the same folder again. Now the results panel left coloumn comes back minimized after the image preview is closed by the user
what is charset normalizer and why is it not found during exe build?
We have lost a lot of speed with the last changes: parallelization of hashing suffers. find the root cause and fix: we need hashing to happen in a multi-threaded way even if a single directory is processed at a time. Maybe more directories hasing running in spearate threads?

Role: Act as a Senior Performance Engineer and Qt Specialist.

Context: I am observing specific performance issues during large scans (30k+ files, 400GB).
CPU Fluctuations: Usage stays at 10-19% for minutes, then spikes to 50-60%.
UI Hang: Windows Task Manager reports "Not Responding," even though work continues in the background.

Task: Analyze the current code and create a plan to implement a Telemetry & Debug Mode. Do not refactor the core logic yet; instead, instrument the code to capture the following metrics:
Stage Timing: Measure the exact time spent in Discovery vs Hashing vs Database Writing.
Lock Contention: Log how long workers are blocked by the threading.Lock() in db.py.
Queue Pressure: Track the size of the ThreadPoolExecutor queue and the backlog of signals being sent to the UI.
Signal Throttling Analysis: Identify if the file_discovered or pixel_hash signals are being emitted too frequently for the Qt Event Loop to process.

Output Requirements:
Propose a PerformanceMonitor class that logs these metrics to a CSV or a dedicated debug console.
Provide a "Hypothesis Report" explaining why the UI is hanging (check for shared locks or signal frequency).
Explain the CPU "Sawtooth" pattern: Is Pass 1 (I/O) starving Pass 2 (CPU), or is the DB batching causing the spikes?