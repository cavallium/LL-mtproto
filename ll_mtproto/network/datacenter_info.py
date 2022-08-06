from concurrent.futures import Executor

from ..crypto import PublicRSA
from ..tl.tl import Schema


class DatacenterInfo:
    __slots__ = ("address", "port", "public_rsa", "schema", "executor")

    address: str
    port: int
    public_rsa: PublicRSA
    schema: Schema
    executor: Executor

    def __init__(self, address: str, port: int, rsa: PublicRSA, schema: Schema, executor: Executor):
        self.address = address
        self.port = port
        self.public_rsa = rsa
        self.schema = schema
        self.executor = executor

    def __copy__(self):
        return DatacenterInfo(self.address, self.port, self.public_rsa, self.schema, self.executor)

    def __str__(self):
        return f"{self.address}:{self.port} (layer: {self.schema.layer})"
