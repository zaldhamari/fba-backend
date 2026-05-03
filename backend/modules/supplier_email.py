def generate_supplier_email(product: str, quantity: int = 500, brand_name: str = "") -> dict:
    subject = f"Inquiry – {product.title()} – OEM/Private Label"

    body = f"""Dear Supplier,

I hope this message finds you well. My name is [Your Name] and I represent {brand_name or '[Your Brand]'}, a brand based in the United States.

I am interested in sourcing **{product}** for sale on Amazon USA under our private label.

Could you please provide the following information:

1. Unit price for MOQ and for 500 / 1,000 / 2,000 units
2. Minimum Order Quantity (MOQ)
3. Sample availability and sample cost
4. Lead time for production and shipping
5. Ability to add our logo and custom packaging
6. Accepted payment methods

We are a serious buyer looking to establish a long-term relationship with a reliable supplier. If the quality and pricing meet our requirements, we plan to place recurring orders.

Please reply with your product catalogue and price list at your earliest convenience.

Thank you for your time and I look forward to hearing from you.

Best regards,
[Your Name]
{brand_name or '[Your Brand]'}
[Your Email]
[Your Phone]"""

    return {
        "subject": subject,
        "body": body,
        "tips": [
            "Always order a sample before placing a bulk order.",
            "Ask for an Alibaba Trade Assurance order for payment protection.",
            "Negotiate — first prices are rarely final.",
            "Ask about Prop 65 compliance if selling in California.",
            "Request product test reports (SGS, BV, Intertek).",
        ],
    }
