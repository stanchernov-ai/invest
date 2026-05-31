import json
import logging
import azure.functions as func

from src.api.auth import require_auth
from src.data.db import fetch_row, fetch_query, execute_query

logger = logging.getLogger(__name__)

bp = func.Blueprint()

@bp.route(route="me", methods=["GET", "PATCH"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def api_me(req: func.HttpRequest) -> func.HttpResponse:
    user_id = req.user_id
    
    if req.method == "GET":
        row = await fetch_row("SELECT profile_json FROM users WHERE id = $1", user_id)
        if not row:
            return func.HttpResponse("Not found", status_code=404)
        return func.HttpResponse(row["profile_json"], mimetype="application/json")
        
    elif req.method == "PATCH":
        try:
            body = req.get_json()
            # Here we would normally merge or replace. For simplicity, replace:
            await execute_query(
                "UPDATE users SET profile_json = $1, updated_at = now() WHERE id = $2",
                json.dumps(body), user_id
            )
            return func.HttpResponse(json.dumps({"status": "ok"}), mimetype="application/json")
        except ValueError:
            return func.HttpResponse("Invalid JSON", status_code=400)


@bp.route(route="portfolios", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def api_portfolios(req: func.HttpRequest) -> func.HttpResponse:
    user_id = req.user_id
    
    if req.method == "GET":
        rows = await fetch_query("SELECT id, name, bucket_type, sort_order FROM portfolios WHERE user_id = $1 ORDER BY sort_order", user_id)
        data = [dict(r) for r in rows]
        # convert UUID to str
        for r in data:
            r['id'] = str(r['id'])
        return func.HttpResponse(json.dumps(data), mimetype="application/json")
        
    elif req.method == "POST":
        try:
            body = req.get_json()
            name = body.get("name")
            bucket_type = body.get("bucket_type", "custom")
            sort_order = body.get("sort_order", 0)
            
            if not name:
                return func.HttpResponse("Missing name", status_code=400)
                
            row = await fetch_row(
                "INSERT INTO portfolios (user_id, name, bucket_type, sort_order) VALUES ($1, $2, $3, $4) RETURNING id",
                user_id, name, bucket_type, sort_order
            )
            return func.HttpResponse(json.dumps({"id": str(row["id"])}), mimetype="application/json", status_code=201)
        except ValueError:
            return func.HttpResponse("Invalid JSON", status_code=400)


@bp.route(route="portfolios/{portfolio_id}/positions", methods=["GET", "PUT"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def api_positions(req: func.HttpRequest) -> func.HttpResponse:
    user_id = req.user_id
    portfolio_id = req.route_params.get('portfolio_id')
    
    # Verify portfolio belongs to user
    portfolio = await fetch_row("SELECT id FROM portfolios WHERE id = $1 AND user_id = $2", portfolio_id, user_id)
    if not portfolio:
        return func.HttpResponse("Not found", status_code=404)
        
    if req.method == "GET":
        rows = await fetch_query(
            "SELECT id, symbol, shares, cost_basis, purchase_date FROM positions WHERE portfolio_id = $1", 
            portfolio_id
        )
        data = [dict(r) for r in rows]
        for r in data:
            r['id'] = str(r['id'])
            r['shares'] = float(r['shares']) if r['shares'] else 0.0
            r['cost_basis'] = float(r['cost_basis']) if r['cost_basis'] else 0.0
            if r['purchase_date']:
                r['purchase_date'] = r['purchase_date'].isoformat()
        return func.HttpResponse(json.dumps(data), mimetype="application/json")
        
    elif req.method == "PUT":
        try:
            positions = req.get_json()
            # Simplistic: delete all and re-insert
            await execute_query("DELETE FROM positions WHERE portfolio_id = $1", portfolio_id)
            for pos in positions:
                sym = pos.get("symbol")
                shares = pos.get("shares", 0)
                cost = pos.get("cost_basis", 0)
                if sym:
                    await execute_query(
                        "INSERT INTO positions (portfolio_id, symbol, shares, cost_basis) VALUES ($1, $2, $3, $4)",
                        portfolio_id, sym, shares, cost
                    )
            return func.HttpResponse(json.dumps({"status": "ok"}), mimetype="application/json")
        except ValueError:
            return func.HttpResponse("Invalid JSON", status_code=400)
