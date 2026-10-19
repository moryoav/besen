# LAN setup

The HACS integration can use local UDP messages for the same entities and controls as Bluetooth. The charger must already be connected to Wi-Fi. This release does not provision a Wi-Fi network or store its name and password.

## Add a charger

Open **Settings** > **Devices & services** > **Add integration** > **Besen**. Enter the charger's IP address or hostname and its 6-digit PIN. Leave the Bluetooth device field empty when setting up LAN. The PIN is the one configured on the charger and used for Bluetooth access.

Home Assistant verifies login, current status and a heartbeat before adding the entry. The charger serial identifies it across IP address changes. A second entry for the same serial is rejected.

## Switch an existing charger

Keep its existing entry. Open its **⋮** menu > **Reconfigure** > **Use LAN**, then enter its address and PIN. Home Assistant releases the current connection before checking LAN. Failed or cancelled validation restores the previous connection. The saved transport changes only after verification. Existing entity IDs, device identity and history are preserved.

Home Assistant checks the saved charger serial to prevent switching the entry to a different charger. If its serial has never been learned, connect over Bluetooth once before selecting LAN.

Use **Reconfigure** > **Use Bluetooth** to switch back. This requires a saved Bluetooth address and a reachable adapter or proxy. An entry first added through LAN does not have a Bluetooth address.

## Network requirements

- Allow inbound UDP **28376** to the Home Assistant host. Chargers send replies, status and announcements to this port.
- Allow outbound UDP from Home Assistant to the charger, normally **7248**. The integration learns the current command port from charger messages.
- Use a DHCP reservation where possible. Announcements can update a known charger's address, but must reach Home Assistant for this to work.
- With containers, use networking that delivers UDP replies and announcements to Home Assistant. Check port mapping, host firewalls and VLAN routing if setup times out. The charger's mobile app and other LAN clients must release their connection first.

One listener serves all configured LAN chargers and concurrent setup flows. It routes messages by serial and closes after its final user unloads. Bluetooth-only entries do not open the UDP listener.

The charger protocol does not encrypt its UDP messages. Use a trusted local network and keep these ports off the public internet.

## Connection failures

During a LAN outage, entities become unavailable and LAN reconnects automatically. This release keeps the selected transport; use Reconfigure to switch to Bluetooth manually. Charging commands are never replayed automatically after a disconnect.

A network timeout does not request a new PIN. If the charger explicitly rejects its saved PIN, follow Home Assistant's reauthentication prompt and enter the current PIN. The replacement is checked over the selected transport before the existing entry is updated.

If setup cannot be verified, check the charger address, Wi-Fi association, PIN and UDP routing. Confirm that no phone app or other client is holding the charger connection. The previous saved connection is kept when a reconfiguration check fails.
