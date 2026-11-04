import os
import time
import threading
from datetime import datetime
import docker
from jose import jwt, JWTError
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="SocketScale Local Fault & Elastic Cluster Controller")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

cli = docker.from_env()
TOKEN = os.getenv("ADMIN_TOKEN", "local-fault-token-change-me")
JWT_SECRET = os.getenv("JWT_SECRET", "local-demo-secret-change-me")

operation_history = []

def verify_token(x_admin_token: str | None = None, authorization: str | None = None):
    # 1. Check local admin token
    if x_admin_token and x_admin_token == TOKEN:
        return True
    # 2. Check JWT Bearer token from Admin user
    if authorization and authorization.startswith("Bearer "):
        try:
            token_str = authorization[7:].strip()
            claims = jwt.decode(token_str, JWT_SECRET, algorithms=["HS256"])
            if claims.get("role") == "admin":
                return True
        except JWTError:
            pass
    raise HTTPException(403, "Invalid admin credentials or unauthorized")

def get_container(name: str):
    try:
        return cli.containers.get(f"socketscale-{name}")
    except docker.errors.NotFound:
        raise HTTPException(404, f"Container socketscale-{name} not found")

def get_all_gateways():
    """Find all containers belonging to the gateway cluster"""
    gateways = []
    for c in cli.containers.list(all=True):
        if c.name.startswith("socketscale-gateway-"):
            node_id = c.name.replace("socketscale-", "")
            gateways.append({
                "node_name": node_id,
                "container_id": c.short_id,
                "status": c.status,
                "created": c.attrs.get("Created")
            })
    # Sort alphabetically (gateway-a, gateway-b, gateway-c, gateway-d...)
    return sorted(gateways, key=lambda x: x["node_name"])

def sync_nginx_upstreams():
    """Dynamically update Nginx upstreams configuration and reload Nginx"""
    try:
        nodes = get_all_gateways()
        # Only route traffic to actively running gateways so stopped containers don't stall Nginx
        running_nodes = [n for n in nodes if n["status"] == "running"]
        if not running_nodes:
            target_nodes = [{"node_name": "gateway-a"}, {"node_name": "gateway-b"}]
        else:
            target_nodes = running_nodes

        server_lines = [
            f"  server {n['node_name']}:8000 max_fails=2 fail_timeout=3s;"
            for n in target_nodes
        ]

        content = "upstream gateways {\n  least_conn;\n" + "\n".join(server_lines) + "\n}\n"
        
        # Write to mounted file
        conf_path = "/app/nginx/upstreams.conf"
        with open(conf_path, "w") as f:
            f.write(content)

        # Trigger zero-downtime hot reload on Nginx
        c_nginx = cli.containers.get("socketscale-nginx")
        reload_res = c_nginx.exec_run("nginx -s reload")
        print(f"[Fault Agent] Nginx reloaded with {len(target_nodes)} gateway upstreams. Output: {reload_res.output}")
    except Exception as e:
        print(f"[Fault Agent] Error syncing Nginx upstreams: {e}")

def execute_container_action_async(container_obj, action: str, delay: float = 0.1):
    def run():
        time.sleep(delay)
        try:
            if action == "stop":
                container_obj.stop(timeout=1)
            elif action == "start":
                container_obj.start()
            elif action == "restart":
                container_obj.restart(timeout=1)

            # If gateway state changed, immediately reload Nginx upstreams
            if container_obj.name.startswith("socketscale-gateway-"):
                time.sleep(0.2)
                sync_nginx_upstreams()
        except Exception as e:
            print(f"[Fault Agent] Error executing {action} on {container_obj.name}: {e}")

    threading.Thread(target=run, daemon=True).start()

# Dynamic Cluster Nodes Management
@app.get("/cluster/gateways")
def list_cluster_gateways(x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    verify_token(x_admin_token, authorization)
    return get_all_gateways()

@app.post("/cluster/gateways/add")
def add_gateway_node(node_name: str | None = None, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    verify_token(x_admin_token, authorization)
    existing = [g["node_name"] for g in get_all_gateways()]

    if not node_name:
        # Determine next available letter: gateway-d, gateway-e, etc.
        alphabet = "abcdefghijklmnopqrstuvwxyz"
        chosen = None
        for char in alphabet:
            cand = f"gateway-{char}"
            if cand not in existing:
                chosen = cand
                break
        node_name = chosen or f"gateway-{int(time.time())}"

    node_name = node_name.strip().lower()
    container_name = f"socketscale-{node_name}"

    try:
        # Check if already exists
        try:
            c = cli.containers.get(container_name)
            if c.status != "running":
                c.start()
                sync_nginx_upstreams()
                return {"status": "started_existing", "node_name": node_name, "container_id": c.short_id}
            raise HTTPException(409, f"Node {node_name} already running")
        except docker.errors.NotFound:
            pass

        # Spawn new container using the gateway image with network aliases
        net_name = "socketscale_default"
        net = cli.networks.get(net_name)

        c = cli.containers.create(
            image="socketscale-gateway-a:latest",
            name=container_name,
            hostname=node_name,
            restart_policy={"Name": "unless-stopped"},
            environment={
                "INSTANCE_ID": node_name,
                "DATABASE_URL": "postgresql+psycopg://socketscale:socketscale@postgres:5432/socketscale",
                "REDIS_URL": "redis://redis:6379/0",
                "JWT_SECRET": JWT_SECRET,
                "FAULT_ADMIN_TOKEN": TOKEN
            }
        )
        net.connect(c, aliases=[node_name, container_name])
        c.start()

        time.sleep(2.0) # Wait brief moment for uvicorn binding
        sync_nginx_upstreams()

        record = {
            "target": node_name,
            "action": "scale_out_add",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "duration_ms": 1500,
            "results": [{"service": node_name, "status": "created", "id": c.short_id}]
        }
        operation_history.append(record)
        return {"status": "created", "node_name": node_name, "container_id": c.short_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to spawn gateway node: {str(e)[:200]}")

@app.delete("/cluster/gateways/{node_name}")
def delete_gateway_node(node_name: str, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    verify_token(x_admin_token, authorization)
    node_name = node_name.strip().lower()
    existing = get_all_gateways()

    if len(existing) <= 1:
        raise HTTPException(400, "Cannot remove the last remaining gateway node in the cluster")

    container_name = f"socketscale-{node_name}"
    try:
        c = cli.containers.get(container_name)
        c.stop(timeout=5)
        c.remove()
        sync_nginx_upstreams()

        record = {
            "target": node_name,
            "action": "scale_in_remove",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "duration_ms": 500,
            "results": [{"service": node_name, "status": "removed"}]
        }
        operation_history.append(record)
        return {"status": "removed", "node_name": node_name}
    except docker.errors.NotFound:
        raise HTTPException(404, f"Gateway node {node_name} not found")
    except Exception as e:
        raise HTTPException(500, f"Failed to delete gateway node: {str(e)[:200]}")

# Services Status (Dynamically includes all active gateway nodes)
@app.get("/services")
def list_services(x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    verify_token(x_admin_token, authorization)
    out = []
    
    # 1. Base infrastructure
    base_infra = ["nginx", "redis", "postgres", "worker", "frontend"]
    for n in base_infra:
        try:
            c = get_container(n)
            c.reload()
            out.append({
                "name": n,
                "status": c.status,
                "container_id": c.short_id,
                "is_gateway": False
            })
        except HTTPException:
            out.append({"name": n, "status": "not_found", "container_id": None, "is_gateway": False})
        except Exception as e:
            out.append({"name": n, "status": "unknown", "error": str(e), "is_gateway": False})

    # 2. Dynamic gateways
    gateways = get_all_gateways()
    for g in gateways:
        out.append({
            "name": g["node_name"],
            "status": g["status"],
            "container_id": g["container_id"],
            "is_gateway": True
        })

    return out

@app.post("/services/{name}/{action}")
def control_service(name: str, action: str, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    verify_token(x_admin_token, authorization)
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(400, "Invalid service operation")

    start_time = time.time()
    results = []

    if name in {"all-gateways", "both-gateways"}:
        targets = [g["node_name"] for g in get_all_gateways()]
    else:
        targets = [name]

    for target in targets:
        c = get_container(target)
        try:
            if action in {"stop", "restart"}:
                execute_container_action_async(c, action, delay=0.3)
                results.append({"service": target, "action": action, "status": "accepted"})
            else:
                c.start()
                results.append({"service": target, "action": action, "status": "success"})
                if c.name.startswith("socketscale-gateway-"):
                    time.sleep(0.5)
                    sync_nginx_upstreams()
        except Exception as exc:
            results.append({"service": target, "action": action, "status": "error", "detail": str(exc)[:200]})

    duration_ms = round((time.time() - start_time) * 1000, 2)
    record = {
        "target": name,
        "action": action,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "duration_ms": duration_ms,
        "results": results
    }
    operation_history.append(record)
    if len(operation_history) > 100:
        operation_history.pop(0)

    return record

@app.get("/history")
def get_history(x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    verify_token(x_admin_token, authorization)
    return operation_history[-30:]

@app.post("/stack/{action}")
def control_stack(action: str, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    verify_token(x_admin_token, authorization)
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(400, "Invalid stack action")

    gw_names = [g["node_name"] for g in get_all_gateways()]
    order = ["postgres", "redis"] + gw_names + ["worker", "frontend", "nginx"]
    if action == "stop":
        order = list(reversed(order))

    start_time = time.time()
    results = []
    for name in order:
        try:
            c = get_container(name)
            if action in {"stop", "restart"}:
                execute_container_action_async(c, action, delay=0.4)
                results.append({"service": name, "status": "accepted"})
            else:
                c.start()
                results.append({"service": name, "status": "success"})
        except Exception as exc:
            results.append({"service": name, "status": "error", "detail": str(exc)[:160]})

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "action": action,
        "duration_ms": duration_ms,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "results": results
    }

@app.post("/recovery/start")
def recovery_start(x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    verify_token(x_admin_token, authorization)

    gw_names = [g["node_name"] for g in get_all_gateways()]
    order = ["postgres", "redis"] + gw_names + ["worker", "frontend", "nginx"]
    results = []
    start_time = time.time()
    for name in order:
        try:
            get_container(name).start()
            results.append({"service": name, "status": "started"})
        except Exception as exc:
            results.append({"service": name, "status": "error", "detail": str(exc)[:160]})

    duration_ms = round((time.time() - start_time) * 1000, 2)
    sync_nginx_upstreams()
    return {
        "action": "start",
        "duration_ms": duration_ms,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "results": results
    }
