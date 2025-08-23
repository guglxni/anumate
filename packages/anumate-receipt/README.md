# Anumate Receipt

This package provides immutable receipt generation for the Anumate platform.

## Usage

To use this package, you can create a `Receipt` object and write it to a WORM storage:

```python
from anumate_receipt import LocalFileSystemWormWriter, Receipt

receipt = Receipt(data={"a": 1, "b": 2})

writer = LocalFileSystemWormWriter("/path/to/storage")
writer.write(receipt)
```

The `Receipt` object automatically calculates a checksum of the data, which can be used to verify the integrity of the receipt.
