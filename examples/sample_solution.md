# Source solution: GPU edge inference pipeline

The solution reduces image-classification latency by using a compact feature encoder followed by a linear classifier.
Its deployment target is an NVIDIA edge GPU with CUDA 12 and at least 4 GB of device memory. The implementation
exports the model to ONNX and runs it with a CUDA execution provider.

The reported success criterion is p95 inference latency below 20 ms for batches of one while maintaining at least
90% accuracy on Dataset-A. The repository includes model weights and an inference script, but does not provide a
CPU benchmark, representative power measurements, or a documented fallback runtime.

The source repository declares an Apache-2.0 license for its code. The documentation does not state the provenance
or redistribution terms of the pretrained weights and Dataset-A.
