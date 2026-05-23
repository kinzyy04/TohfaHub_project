import re

with open("alembic/versions/3580e80a656e_add_order_models.py", "r") as f:
    c = f.read()

c = re.sub(r"    op\.alter_column\('audit_logs'.*?# ### end Alembic commands ###", "    # ### end Alembic commands ###", c, flags=re.DOTALL)
c = re.sub(r"    op\.alter_column\('users'.*?op\.drop_index", "    op.drop_index", c, flags=re.DOTALL)

with open("alembic/versions/3580e80a656e_add_order_models.py", "w") as f:
    f.write(c)
