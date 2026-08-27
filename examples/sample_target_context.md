# Target context: CPU-only industrial gateway

The target project runs on an x86 industrial gateway with four CPU cores, 8 GB of system memory, and no discrete GPU.
The application processes one image at a time and requires p95 end-to-end latency below 30 ms. A temporary accuracy
floor of 88% is acceptable during feasibility testing.

The team can export ONNX models and collect 2,000 representative target-domain images. It cannot add cloud inference
or new accelerator hardware. The evaluation must include latency, peak memory, accuracy under domain shift, and
license or provenance review for every redistributed model and dataset artifact.
