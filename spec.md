# Odoo to API Sync - Specification

## Purpose

A Python worker designed to continuously poll an Odoo Helpdesk instance for new tickets and broadcast an alert to a WhatsApp group via the API.

## Architecture & Stack

- **Language**: Python 3.11+
- **Core Dependencies**:
  - `requests` (for REST API integration)
  - `python-dotenv` (for environment variable management)
  - `xmlrpc.client` (built-in, for Odoo API interaction)
- **Execution Model**: Long-running process (infinite loop) with a 60-second sleep interval (`time.sleep(60)`).
- **State Management**:
  - Uses a plain text file (`last_ticket_id.txt`) to keep track of the latest processed ticket ID.
  - In a Docker environment (detected by the presence of `/app/data`), the state file is stored at `/app/data/last_ticket_id.txt` to leverage Docker volumes.
  - In a local environment, the file is saved in the script's root directory.

## Core Logic Flow

1. **Load Configuration**: Reads credentials and API endpoints from environment variables (`.env`).
2. **Odoo Authentication**: Connects via XML-RPC to Odoo and authenticates the user.
3. **Read State**: Retrieves the `last_id` from the state file. If `0` (first run), it finds the highest existing ticket ID and sets it as the starting point to avoid spamming old tickets.
4. **Fetch New Tickets**: Queries Odoo for `helpdesk.ticket` where `id > last_id` in ascending order.
5. **Enrich Data**: Reads specific fields: `id`, `name`, `stage_id`, `description`, `user_id`, `partner_id`, `priority`.
6. **Filtering**: Processes only tickets whose stage name contains "New" or "Nuevo".
7. **Formatting**: Builds a WhatsApp message string injecting ticket ID, stars (based on priority), title, client name, and assigned user.
8. **Notification**: Sends a POST payload to the API.
9. **Update State**: Records the latest processed ticket ID to the state file.
10. **Loop**: Sleeps for 60 seconds and repeats.
