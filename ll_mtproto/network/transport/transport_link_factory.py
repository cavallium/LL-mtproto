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


import abc

from ll_mtproto.network.datacenter_info import DatacenterInfo
from ll_mtproto.network.transport.transport_link_base import TransportLinkBase

__all__ = ("TransportLinkFactory",)


class TransportLinkFactory(abc.ABC):
    @abc.abstractmethod
    def new_transport_link(self, datacenter: DatacenterInfo) -> TransportLinkBase:
        raise NotImplementedError
