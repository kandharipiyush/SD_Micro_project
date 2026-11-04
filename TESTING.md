# SocketScale verification checklist

Run after `docker compose up --build -d`. Mark each test only after observing the result on your machine.

- [ ] `docker compose ps` shows frontend, both gateways, Nginx, Redis, PostgreSQL, worker and fault-agent running.
- [ ] `http://localhost:8080` loads and `http://localhost:8080/docs` opens API documentation.
- [ ] Admin login works; register two new user accounts.
- [ ] Open two separate browser profiles and verify each user can send and receive room messages.
- [ ] Create a room and verify it appears for both users.
- [ ] Send messages, refresh/reconnect the second user, and verify history loads from PostgreSQL.
- [ ] Stop Gateway A and verify new connections continue through Gateway B; restart Gateway A.
- [ ] Repeat for Gateway B.
- [ ] Stop Redis, send a message, restart Redis, and verify the outbox worker eventually publishes the pending message.
- [ ] Stop PostgreSQL and verify health degrades and message persistence fails; restart and verify recovery.
- [ ] Stop/restart Nginx and verify entry-point recovery.
- [ ] Run benchmark commands for 10, 25 and 50 clients × 20 messages. Save the actual JSON output.
- [ ] Confirm benchmark results appear in the admin Performance page.
- [ ] Test Stack OFF/ON last; confirm fault-agent remains available to restart the stack.

Do not mark tests as passed based only on the source code. Record actual values and any failures in your project report.
