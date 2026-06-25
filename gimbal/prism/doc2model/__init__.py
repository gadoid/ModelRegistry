"""gimbal.prism.doc2model — back-compat shim re-exporting the split modules.

The actual code now lives in:
  - doc2model.infer:   safe_name, classify_value, merge_types, collect_field_stats
  - doc2model.codegen: emit_model, generate_models, write_registry_file, build_endpoint_module
  - doc2model.cli:     load_samples, main (argparse entry)
"""
from gimbal.prism.doc2model.cli import main, load_samples

__all__ = ["main", "load_samples"]