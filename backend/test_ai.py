from services.ai_service import analyze_lead_reply


reply = "Yes, I am interested. Please tell me more."

result = analyze_lead_reply(reply)

print("Intent:", result)