"""Edge gateway: polls the furnace meter over Modbus TCP and forwards readings, offline-first.

Every reading goes into a local SQLite outbox first. A forwarder sends batches
to the MeltWise API and deletes them only after the API accepts them, so a
network or power cut on the shop floor delays data but never loses it.
"""

import json
import sqlite3
import threading
import time

import httpx
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from .meter_sim import DI_LID, FLOAT32, REG_ENERGY, REG_MELT, REG_POWER, REG_SECONDS


class Gateway:
    def __init__(self, api_url, outbox_path, host="127.0.0.1", port=5020, device="furnace-1",
                 poll_s=0.25, batch=40):
        self.api_url, self.device, self.poll_s, self.batch = api_url.rstrip("/"), device, poll_s, batch
        self.client = ModbusTcpClient(host, port=port)
        self.db = sqlite3.connect(outbox_path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL)")
        self.db.commit()
        self.lock = threading.Lock()
        self.last_key = None
        self.stored = self.sent = self.failed_posts = 0

    def _snapshot(self):
        """Read power, energy, seconds and melt number in one request, so they always belong together."""
        response = self.client.read_holding_registers(0, count=8, device_id=1)
        if response.isError():
            raise IOError(f"Modbus read failed: {response}")
        regs = response.registers
        value = lambda reg: float(self.client.convert_from_registers(regs[reg:reg + 2], FLOAT32))
        return {"power_kw": value(REG_POWER), "energy_kwh": value(REG_ENERGY),
                "t_s": value(REG_SECONDS), "melt_no": int(value(REG_MELT))}

    def read(self):
        """One reading from the meter, or None if the meter has not moved on since the last poll."""
        if not self.client.connected and not self.client.connect():
            return None
        snap = self._snapshot()
        lid = self.client.read_discrete_inputs(DI_LID, count=1, device_id=1)
        if (snap["melt_no"], snap["t_s"]) == self.last_key:
            return None
        self.last_key = (snap["melt_no"], snap["t_s"])
        return {"device": self.device, "melt_no": snap["melt_no"], "t_s": snap["t_s"],
                "power_kw": round(snap["power_kw"], 2), "energy_kwh": round(snap["energy_kwh"], 3),
                "lid_open": bool(lid.bits[0]), "read_at": time.time()}

    def store(self, reading):
        with self.lock:
            self.db.execute("INSERT INTO outbox (body) VALUES (?)", (json.dumps(reading),))
            self.db.commit()
            self.stored += 1

    def pending(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]

    def flush(self):
        """Send buffered readings in order; stop at the first failure and keep the rest."""
        while True:
            with self.lock:
                rows = self.db.execute("SELECT id, body FROM outbox ORDER BY id LIMIT ?", (self.batch,)).fetchall()
            if not rows:
                return True
            try:
                response = httpx.post(f"{self.api_url}/api/ingest", json={"readings": [json.loads(b) for _, b in rows]},
                                      timeout=3.0)
                response.raise_for_status()
            except httpx.HTTPError:
                self.failed_posts += 1
                return False
            with self.lock:
                self.db.execute("DELETE FROM outbox WHERE id <= ?", (rows[-1][0],))
                self.db.commit()
            self.sent += len(rows)

    def run(self, stop, flush_every=4):
        polls = 0
        while not stop.is_set():
            try:
                reading = self.read()
            except (IOError, ModbusException):   # meter offline or rebooting: keep polling
                self.client.close()
                reading = None
            if reading:
                self.store(reading)
            polls += 1
            if polls % flush_every == 0:
                self.flush()
            time.sleep(self.poll_s)
        self.flush()
        self.client.close()

    def start(self, stop):
        thread = threading.Thread(target=self.run, args=(stop,), daemon=True)
        thread.start()
        return thread
