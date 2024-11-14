# Copyright (C) 2017-2018 (nikat) https://github.com/nikat/mtproto2json
# Copyright (C) 2020-2024 (andrew) https://github.com/andrew-ld/LL-mtproto

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

__all__ = ("TransportProxySocks5Info",)


class TransportProxySocks5Info:
    __slots__ = (
        "address",
        "port",
        "user",
        "password"
    )

    address: str
    port: int
    user: str
    password: str

    def __init__(self, address: str, port: int, user: str, password: str):
        self.address = address
        self.port = port
        self.user = user
        self.password = password