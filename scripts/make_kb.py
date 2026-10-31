from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "kb"

DOCS = [
    ("KB-01", "return-policy", "Return Policy", """
- Items can be returned within 30 days of the delivery date.
- Items must be unused and in original packaging, except damaged, defective, or wrong items (see KB-02, KB-03, KB-09).
- Standard customers pay $6 return shipping unless the item was damaged, defective, or wrong. Gold members always return free (KB-14).
- Gold members get a 45-day window instead of 30 (KB-14).
- Clearance, custom, and gift card purchases are final sale (KB-15).
- Refunds go to the original payment method (KB-07).
"""),
    ("KB-02", "damaged-items", "Damaged Items", """
- Applies when an item arrives broken, cracked, crushed, or otherwise damaged.
- The customer must report it within 30 days of delivery.
- At least one photo of the damage is required. If there is no photo, ask for one before deciding anything.
- With a photo, the customer may choose a full refund or a free replacement (subject to stock).
- No return is needed if the order total is under $50. Above $50, send a prepaid return label.
- Refunds above $100 need human approval (KB-08).
"""),
    ("KB-03", "wrong-item", "Wrong Item Received", """
- Applies when the item delivered is not the item ordered.
- The customer must report it within 30 days of delivery.
- Ask for a photo of the item received and of the shipping label.
- We either ship the correct item free or give a full refund. Return shipping for the wrong item is always free.
- Refunds above $100 need human approval (KB-08).
"""),
    ("KB-04", "missing-package", "Missing Package", """
- Applies when tracking says delivered but the customer has not received it, or the order is far past its delivery estimate.
- First ask the customer to check with household members, neighbors, or the mailroom, and to wait 48 hours after the delivered scan.
- After 48 hours, open a carrier investigation, which takes 3 to 5 business days.
- If the package is not found, offer a replacement or a full refund.
- Refunds above $100 need human approval (KB-08).
- Do not promise an outcome before the investigation finishes.
"""),
    ("KB-05", "shipping-and-delays", "Shipping Times and Delays", """
- Standard shipping takes 3 to 7 business days from the shipped date and is free on orders over $50.
- Express shipping takes 1 to 3 business days and costs $12.
- Orders in "placed" status ship within 2 business days.
- An order in "shipped" status for more than 10 business days with no delivery is treated as missing (KB-04).
- If express shipping was paid and delivery took more than 3 business days, refund the $12 express fee.
- Shipping fees are otherwise not refunded for delays.
"""),
    ("KB-06", "order-cancellation", "Order Cancellation", """
- An order can be cancelled only while its status is "placed".
- Once the status is "shipped", it cannot be cancelled. The customer may refuse delivery or return it after delivery under KB-01.
- If the order is already "delivered", use the return policy (KB-01).
- Cancelled orders are refunded in full within 3 to 5 business days.
"""),
    ("KB-07", "refund-timing", "Refund Timing and Status", """
- A refund is issued within 3 business days after approval, or after a return is received and inspected (2 to 3 business days).
- After issue, the customer's bank may take 5 to 7 more business days to show the money.
- If the order status is "refunded", the refund was already issued. Ask the customer to check with their bank after 7 days.
- If the money has not appeared after 10 business days, escalate to the billing team (KB-10).
- Refunds go only to the original payment method.
"""),
    ("KB-08", "refund-approval-limits", "Refund Approval Limits", """
- The support agent may approve a refund up to $100 (order total) when a policy clearly applies.
- Above $100, the agent drafts the reply and recommendation, but a human must approve.
- Never approve a refund outside the policy windows without human review.
- Never approve a refund on an order whose status is "cancelled" or "refunded".
- A customer with 3 or more tickets in the last 30 days always goes to a human (KB-16).
"""),
    ("KB-09", "warranty-and-defects", "Warranty and Defects", """
- Electronics have a 12-month warranty for manufacturing defects.
- Home items have a 90-day warranty.
- Apparel and accessories are covered only by the 30-day return window.
- Warranty does not cover accidental damage, water damage, or misuse.
- A defect found within 30 days is handled as a return with refund or replacement (KB-01).
- A defect after 30 days but within warranty goes to the warranty team: escalate to a human with the order and a description of the defect.
"""),
    ("KB-10", "billing-issues", "Billing and Duplicate Charges", """
- Duplicate charge: confirm two charges exist for the same order. If confirmed, refund the duplicate within 3 business days.
- Unrecognized charge: ask for the last 4 digits of the card and the charge date, then escalate to the billing team.
- Wrong amount charged: escalate to the billing team.
- Never ask for a full card number, CVV, or password.
"""),
    ("KB-11", "promo-and-price-adjustments", "Promo Codes and Price Adjustments", """
- Promo codes must be applied at checkout and cannot be added after an order is placed.
- Only one promo code can be used per order, and expired codes cannot be honored.
- If an item's price drops within 14 days of purchase, the customer may request an adjustment for the difference.
- A price adjustment is a refund and follows the approval limits in KB-08.
"""),
    ("KB-12", "address-changes", "Address Changes", """
- The shipping address can be changed only while the order status is "placed".
- Once the order is "shipped", the address cannot be changed. The customer can contact the carrier or refuse delivery.
- Confirm any address change by email to the address on file.
"""),
    ("KB-13", "account-access", "Account Access", """
- Password resets are done only through an emailed link that is valid for 1 hour.
- We never reset passwords by chat or phone, and we never ask for a password.
- After 5 failed login attempts, the account is locked for 30 minutes.
- Account deletion and data requests go to the privacy team: escalate, and do not promise a timeline.
"""),
    ("KB-14", "gold-membership", "Gold Membership Benefits", """
- Gold members get a 45-day return window, free return shipping, and priority support.
- Check the customer's tier in their customer record.
- Gold status does not change the refund approval limit (KB-08).
"""),
    ("KB-15", "non-returnable-items", "Non-Returnable Items", """
- Clearance items marked final sale, custom or personalized items, and gift cards cannot be returned.
- Exception: damaged, defective, or wrong items are still covered by KB-02, KB-03, and KB-09.
"""),
    ("KB-16", "escalation-rules", "Escalation Rules", """
- Always escalate to a human when the customer mentions a lawyer, lawsuit, or chargeback.
- Always escalate when the customer reports an injury or safety hazard (KB-17).
- Always escalate for 3 or more tickets from the same customer in 30 days.
- Always escalate when no policy applies, when policies conflict, or when the customer asks for a human.
- Always escalate refunds above $100 (KB-08).
- An escalation note includes a summary, the order details, the policy cited, and a recommended action.
- Never promise compensation outside policy.
"""),
    ("KB-17", "product-safety", "Product Safety Issues", """
- Applies to overheating, smoke, sparks, battery swelling, or any injury.
- Tell the customer to stop using the product and unplug it immediately.
- Do not offer troubleshooting.
- Escalate to a human as high priority. A human decides on refund or replacement.
"""),
]


def main() -> None:
    KB_DIR.mkdir(exist_ok=True)
    for old in KB_DIR.glob("KB-*.md"):
        old.unlink()
    for doc_id, slug, title, body in DOCS:
        text = f"# {doc_id}: {title}\n\n{body.strip()}\n"
        (KB_DIR / f"{doc_id}-{slug}.md").write_text(text)
    print(f"Wrote {len(DOCS)} documents to {KB_DIR}")


if __name__ == "__main__":
    main()