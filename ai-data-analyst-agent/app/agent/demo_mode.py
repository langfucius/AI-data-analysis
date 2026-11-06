"""Deterministic SQL templates used when no OpenAI API key is configured."""
from __future__ import annotations


def demo_sql(question: str) -> tuple[str, str]:
    q = question.lower()

    if ("category" in q or "类别" in q or "品类" in q) and any(
        word in q for word in ("sales", "revenue", "销售", "收入")
    ):
        return (
            """
            SELECT p.category,
                   ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue,
                   SUM(oi.quantity) AS units_sold
            FROM order_items oi
            JOIN products p ON p.product_id = oi.product_id
            JOIN orders o ON o.order_id = oi.order_id
            WHERE o.status = 'delivered'
            GROUP BY p.category
            ORDER BY revenue DESC
            """,
            "Demo Mode selected a category revenue analysis template."
        )

    if any(word in q for word in ("top product", "best-selling", "best selling",
                                  "popular product", "畅销产品", "最畅销")):
        return (
            """
            SELECT p.product_name,
                   p.category,
                   SUM(oi.quantity) AS units_sold,
                   ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
            FROM order_items oi
            JOIN products p ON p.product_id = oi.product_id
            JOIN orders o ON o.order_id = oi.order_id
            WHERE o.status = 'delivered'
            GROUP BY p.product_id, p.product_name, p.category
            ORDER BY revenue DESC
            LIMIT 5
            """,
            "Demo Mode selected a top-products analysis template."
        )

    if any(word in q for word in ("monthly", "month", "trend", "每月", "月度", "趋势", "走势", "高点")):
        return (
            """
            SELECT strftime('%Y-%m', order_date) AS month,
                   ROUND(SUM(total_amount), 2) AS revenue,
                   COUNT(*) AS delivered_orders
            FROM orders
            WHERE status = 'delivered'
            GROUP BY strftime('%Y-%m', order_date)
            ORDER BY month
            """,
            "Demo Mode selected a monthly revenue trend template."
        )

    if any(word in q for word in ("top customer", "best customer", "highest spending",
                                  "客户消费", "高价值客户")):
        return (
            """
            SELECT c.customer_name,
                   c.city,
                   ROUND(SUM(o.total_amount), 2) AS total_spending,
                   COUNT(o.order_id) AS delivered_orders
            FROM customers c
            JOIN orders o ON o.customer_id = c.customer_id
            WHERE o.status = 'delivered'
            GROUP BY c.customer_id, c.customer_name, c.city
            ORDER BY total_spending DESC
            LIMIT 10
            """,
            "Demo Mode selected a top-customers analysis template."
        )

    if any(word in q for word in ("average order", "aov", "平均订单")):
        return (
            """
            SELECT ROUND(AVG(total_amount), 2) AS average_order_value,
                   COUNT(*) AS delivered_orders
            FROM orders
            WHERE status = 'delivered'
            """,
            "Demo Mode selected an average-order-value template."
        )

    if any(word in q for word in ("status", "订单状态", "order status")):
        return (
            """
            SELECT status, COUNT(*) AS order_count
            FROM orders
            GROUP BY status
            ORDER BY order_count DESC
            """,
            "Demo Mode selected an order-status distribution template."
        )

    if any(word in q for word in ("count", "number of orders", "how many orders",
                                  "订单数量", "多少订单")):
        return (
            "SELECT COUNT(*) AS total_orders FROM orders",
            "Demo Mode selected an order-count template."
        )

    if any(word in q for word in ("revenue", "sales", "销售额", "总收入", "营收")):
        return (
            """
            SELECT ROUND(SUM(total_amount), 2) AS total_revenue,
                   COUNT(*) AS delivered_orders
            FROM orders
            WHERE status = 'delivered'
            """,
            "Demo Mode selected a total-revenue template."
        )

    raise ValueError('Demo 模式未识别此查询，请使用示例问题，或配置模型 API 后自由提问。')
