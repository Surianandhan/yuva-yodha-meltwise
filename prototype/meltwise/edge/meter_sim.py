"""A Modbus TCP energy meter that plays simulated melts, standing in for the furnace panel meter.

The register map is this prototype's own. For a real Schneider EM6400NG or
PowerLogic meter, set the addresses from that meter's Modbus register list;
the gateway reads them the same way.

Holding registers (float32, big-endian word order, two registers each):
  0  active power, kW
  2  active energy since melt start, kWh
  4  seconds since melt start (demo only; a real gateway timestamps readings itself)
  6  melt number
Discrete input 0: lid open. In the kit this is a limit switch on the gateway's own digital input.
"""

import asyncio
import threading

from pymodbus.client import ModbusTcpClient
from pymodbus.server import ServerAsyncStop, StartAsyncTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

REG_POWER, REG_ENERGY, REG_SECONDS, REG_MELT = 0, 2, 4, 6
DI_LID = 0
FLOAT32 = ModbusTcpClient.DATATYPE.FLOAT32
FC_READ_DISCRETE, FC_READ_HOLDING = 2, 3


class MeterSimulator:
    """Serves one reading per melt step; `speed` compresses time (40 = a 75-minute melt in under 2 minutes)."""

    def __init__(self, melts, host="127.0.0.1", port=5020, speed=40.0):
        self.melts, self.host, self.port, self.speed = melts, host, port, speed
        self.values = {REG_POWER: 0.0, REG_ENERGY: 0.0, REG_SECONDS: 0.0, REG_MELT: 0.0}
        self.lid_open = False
        self.position = (0, 0)  # (melt number, step) currently shown
        self.finished = threading.Event()
        self.device = SimDevice(
            id=1,
            simdata=([SimData(0, count=8, values=False, datatype=DataType.BITS)],
                     [SimData(0, count=8, values=False, datatype=DataType.BITS)],
                     [SimData(0, count=16, values=0, datatype=DataType.REGISTERS)],
                     [SimData(0, count=1, values=0, datatype=DataType.REGISTERS)]),
            action=self._on_request,
        )
        if melts:  # never serve placeholder zeros: show the first real reading from the start
            self._show(0, 0, melts[0].power_kw[0] * 10.0 / 3600.0)

    async def _on_request(self, function_code, start_address, address, count, current_registers, set_values):
        """Fill the registers a client is reading from the meter's current state."""
        if function_code == FC_READ_HOLDING:
            for reg, value in self.values.items():
                words = ModbusTcpClient.convert_to_registers(float(value), FLOAT32)
                for offset, word in enumerate(words):
                    index = reg + offset - start_address
                    if 0 <= index < len(current_registers):
                        current_registers[index] = word
        elif function_code == FC_READ_DISCRETE and 0 <= DI_LID - start_address < len(current_registers):
            current_registers[DI_LID - start_address] = self.lid_open
        return None

    def _show(self, melt_no, step, energy):
        record = self.melts[melt_no]
        self.values = {REG_POWER: record.power_kw[step], REG_ENERGY: energy,
                       REG_SECONDS: record.t_s[step], REG_MELT: melt_no}
        self.lid_open = bool(record.lid_open[step])
        self.position = (melt_no, step)

    async def _play(self):
        for melt_no, record in enumerate(self.melts):
            energy = 0.0
            for step in range(len(record.t_s)):
                energy += record.power_kw[step] * 10.0 / 3600.0
                self._show(melt_no, step, energy)
                await asyncio.sleep(10.0 / self.speed)
        self.finished.set()

    async def _main(self):
        server = asyncio.create_task(StartAsyncTcpServer(context=self.device, address=(self.host, self.port)))
        await asyncio.sleep(0.5)
        await self._play()
        await asyncio.sleep(2.0)
        await ServerAsyncStop()
        server.cancel()

    def start(self):
        """Run the meter in a background thread."""
        thread = threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True)
        thread.start()
        return thread
