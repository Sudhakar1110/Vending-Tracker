**Restock Completed**

Stock Entry **{{ doc.name }}** has been submitted.

- Machine: {{ doc.custom_vending_machine }}
- Type: {{ doc.stock_entry_type }}
- From: {{ doc.from_warehouse or '—' }}
- To: {{ doc.to_warehouse or '—' }}
