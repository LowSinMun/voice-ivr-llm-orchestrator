import os
import re
import sys
import uvicorn
import pandas as pd

from fastapi import FastAPI
from pydantic import BaseModel
from pyngrok import ngrok
from typing import Optional


# ===============================
# FastAPI App
# ===============================

app = FastAPI(title="ABC Mock IVR API")


# ===============================
# Ngrok Config
# ===============================
# Demo setup:
# - Prefer NGROK_TOKEN from environment if it exists.
# - Otherwise use the fallback token below so start_button.bat can directly print the ngrok public URL.

NGROK_TOKEN = os.getenv("NGROK_TOKEN")
if not NGROK_TOKEN:
    raise ValueError("NGROK_TOKEN environment variable is missing!")

try:
    print("Starting ngrok tunnel...")
    ngrok.set_auth_token(NGROK_TOKEN)
    tunnel = ngrok.connect(8000)

    print("\n" + "=" * 60)
    print(f"NGROK PUBLIC URL: {tunnel.public_url}")
    print("=" * 60 + "\n")

except Exception as e:
    print(f"Ngrok failed to start: {e}")
    sys.exit(1)


# ===============================
# Mock Database
# ===============================

mock_data = {
    "Name": [
        "Cust A",
        "Cust B",
        "Cust C"
    ],
    "NRIC": [
        "YYMMDDLLXXXX",
        "YYMMDDLLXXXX",
        "YYMMDDLLXXXX"
    ],
    "Credit_Card_Number": [
        "5111XXXXXXXX1111",
        "4500XXXXXXXX0004",
        "4200XXXXXXXX8211"
    ],
    "Credit_Card_Activation_Status": [
        "Active",
        "Active",
        "Inactive"
    ],
    "Credit_Card_Name": [
        "ABC World MasterCard",
        "CDE Premier Visa",
        "FGH Platinum Business"
    ]
}

df = pd.DataFrame(mock_data)


# ===============================
# Session Memory
# ===============================
# 每通电话一个 session。
# failed_attempts 只记录“IC 或信用卡验证错误”的次数。
# 第 1 次错：retry
# 第 2 次错：retry
# 第 3 次错：handoff 转人工

MAX_FAILED_ATTEMPTS = 5

session_cache = {}


# ===============================
# Request Models
# ===============================

class AuthRequest(BaseModel):
    session_id: str
    nric: Optional[str] = None
    last_4_cc: Optional[str] = None


class CreateSRRequest(BaseModel):
    session_id: Optional[str] = None
    customer_name: Optional[str] = None
    nric: Optional[str] = None
    last_4_cc: Optional[str] = None


# ===============================
# Helper Functions
# ===============================

def clean_digits(value: Optional[str]) -> Optional[str]:
    """
    Remove spaces, hyphens, and non-digit characters.
    Example:
    YYMMDD-LL-XXXX -> YYMMDDLLXXXX
    """
    if value is None:
        return None

    value = str(value).strip()
    if not value:
        return None

    digits = re.sub(r"\D", "", value)
    return digits if digits else None


def get_session(session_id: str) -> dict:
    if session_id not in session_cache:
        session_cache[session_id] = {
            "failed_attempts": 0,
            "verified_nric": None,
            "handoff_locked": False
        }

    return session_cache[session_id]


def build_response(
    status: str,
    message: str,
    cache: Optional[dict] = None,
    should_upsell: bool = False,
    **extra
) -> dict:
    response = {
        "status": status,
        "message": message,
        "should_upsell": should_upsell
    }

    if cache is not None:
        response.update({
            "failed_attempts": cache.get("failed_attempts", 0),
            "max_failed_attempts": MAX_FAILED_ATTEMPTS,
            "remaining_attempts": max(
                0,
                MAX_FAILED_ATTEMPTS - cache.get("failed_attempts", 0)
            )
        })

    response.update(extra)
    return response


def handle_invalid_customer_info(cache: dict) -> dict:
    """
    Called only when customer provided both fields,
    but IC or card last 4 digits is incorrect.
    """
    cache["failed_attempts"] += 1

    # 第 3 次错误：转人工
    if cache["failed_attempts"] > MAX_FAILED_ATTEMPTS:
        cache["handoff_locked"] = True

        return build_response(
            status="handoff",
            message="Maximum verification attempts reached. I will transfer you to a live agent now.",
            cache=cache,
            should_upsell=False,
            next_action="transfer_to_live_agent"
        )

    # 第 1-2 次错误：让客户重试
    return build_response(
        status="retry",
        message="Your IC and credit card number are invalid. Please provide the correct IC number and the last 4 digits of your credit card.",
        cache=cache,
        should_upsell=False,
        next_action="retry_verification"
    )


# ===============================
# API Endpoints
# ===============================

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "message": "ABC Mock IVR API is running."
    }


@app.post("/api/verify_and_check_status")
def verify_and_check_status(req: AuthRequest):
    session_id = req.session_id

    if not session_id:
        return {
            "status": "handoff",
            "message": "Unable to verify the call session. I will transfer you to a live agent now.",
            "should_upsell": False,
            "next_action": "transfer_to_live_agent"
        }

    cache = get_session(session_id)

    # 如果这通电话已经达到转人工状态，后续不再验证
    if cache.get("handoff_locked"):
        return build_response(
            status="handoff",
            message="Maximum verification attempts reached. I will transfer you to a live agent now.",
            cache=cache,
            should_upsell=False,
            next_action="transfer_to_live_agent"
        )

    nric_to_check = clean_digits(req.nric) or cache.get("verified_nric")
    cc_to_check = clean_digits(req.last_4_cc)

    # 缺资料不算错误次数
    if not nric_to_check or not cc_to_check:
        return build_response(
            status="prompt_required_info",
            message="Please provide your IC number and the last 4 digits of your credit card.",
            cache=cache,
            should_upsell=False,
            next_action="collect_required_info"
        )

    # 格式明显不对，算验证错误
    if len(nric_to_check) != 12 or len(cc_to_check) != 4:
        return handle_invalid_customer_info(cache)

    # ===============================
    # 1. Verify NRIC
    # ===============================

    user = df[df["NRIC"] == nric_to_check]

    if user.empty:
        return handle_invalid_customer_info(cache)

    # NRIC 正确，保存记忆
    cache["verified_nric"] = nric_to_check

    # ===============================
    # 2. Verify Card Last 4 Digits
    # ===============================

    actual_cc = str(user.iloc[0]["Credit_Card_Number"])

    if not actual_cc.endswith(cc_to_check):
        return handle_invalid_customer_info(cache)

    # ===============================
    # 3. Verify Card Status
    # ===============================

    card_status = str(user.iloc[0]["Credit_Card_Activation_Status"])

    if card_status.lower() != "active":
        return build_response(
            status="rejected",
            message="Your credit card is currently not active. We cannot activate overseas transactions. Please contact a live agent for further assistance.",
            cache=cache,
            should_upsell=False,
            customer_name=user.iloc[0]["Name"],
            card_name=user.iloc[0]["Credit_Card_Name"],
            next_action="stop_no_upsell"
        )

    # ===============================
    # 4. Success
    # ===============================

    customer_name = user.iloc[0]["Name"]
    card_name = user.iloc[0]["Credit_Card_Name"]

    # 验证成功后清掉 session 记忆
    if session_id in session_cache:
        del session_cache[session_id]

    return build_response(
        status="success",
        message="Authentication successful. Your card is active and eligible for overseas transaction activation.",
        should_upsell=True,
        customer_name=customer_name,
        card_name=card_name,
        next_action="create_sr_and_upsell"
    )


@app.post("/api/create_sr")
def create_sr(req: Optional[CreateSRRequest] = None):
    """
    Mock CRM Service Request creation.
    n8n 应该只在 verify_and_check_status 返回 status == success 时调用这个 endpoint。
    """

    return {
        "status": "success",
        "sr_number": "SR-889922",
        "message": "Service Request successfully created in CRM."
    }


@app.get("/api/debug/sessions")
def debug_sessions():
    """
    本地测试用。
    生产环境不要开放这个 endpoint。
    """
    return session_cache


@app.delete("/api/debug/sessions/{session_id}")
def clear_session(session_id: str):
    """
    本地测试用：手动清除某个 session。
    """
    if session_id in session_cache:
        del session_cache[session_id]

    return {
        "status": "success",
        "message": f"Session {session_id} cleared."
    }


# ===============================
# Run Server
# ===============================

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000
    )