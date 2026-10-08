"""Fixed runtime gate for confirmed operations, Python2.6 stdlib only.

Runtime/registration objects are hash-bound operator configuration, never MCP
arguments. Confirmation is read, never authored, by this execution module.
"""

# mypy: ignore-errors
import os
from decimal import Decimal, localcontext

PLAN_KEYS = (
    "schema_version",
    "resource_domain_sha256",
    "runner_sha256",
    "ledger_ref",
    "environment_sha256",
    "design_sha256",
    "pdk_sha256",
    "grant_sha256",
    "request",
    "analysis",
    "attempt_cost",
    "accounting",
)
BINDINGS = ("environment_sha256", "design_sha256", "pdk_sha256")


class ConfirmedGate(object):
    def __init__(
        self, profile, profile_raw, registration, runtime_sha, probe_sha, modules, activation=None
    ):
        # modules is supplied only by the verified runtime loader, not JSON.
        self.profile, self.profile_raw = profile, profile_raw
        self.registration, self.runtime_sha = registration, runtime_sha
        self.probe_sha = probe_sha
        self.activation = activation
        self.accounting, self.confirmation, self.probe, self.storage, self.copying = modules
        self.root = profile["paths"]["managed_root"]
        self.anchor = registration["identity_manifest_sha256"]
        if set(registration) != set(
            ("schema_version", "identity_manifest_sha256", "routes") + BINDINGS
        ):
            raise ValueError("native_gate_registration_shape")
        if type(registration["schema_version"]) is not int or registration["schema_version"] != 1:
            raise ValueError("native_gate_registration_version")
        if registration["environment_sha256"] != self.accounting.digest(profile_raw):
            raise ValueError("native_gate_environment_binding")
        for key in BINDINGS + ("identity_manifest_sha256",):
            if not self.accounting.matches(self.accounting.HASH, registration[key]):
                raise ValueError("native_gate_registration_digest")
        if not self.accounting.matches(self.accounting.HASH, runtime_sha):
            raise ValueError("native_gate_runtime_digest")
        routes = registration["routes"]
        if not isinstance(routes, list) or not 1 <= len(routes) <= 48:
            raise ValueError("native_gate_route_bound")
        identities = [(r["design_id"], r["analysis_id"]) for r in routes]
        if len(identities) != len(set(identities)):
            raise ValueError("native_gate_duplicate_route")

    def route(self, plan):
        request = plan["request"]
        routes = [
            r
            for r in self.registration["routes"]
            if (r["design_id"], r["analysis_id"]) == (request["design_id"], request["analysis_id"])
        ]
        if len(routes) != 1 or routes[0]["analysis"] != plan["analysis"]:
            raise ValueError("native_gate_unregistered_analysis")
        return routes[0]

    def identity(self, plan):
        if set(plan) != set(PLAN_KEYS) or (
            type(plan["schema_version"]) is not int
            or plan["schema_version"] != 1
            or type(plan["attempt_cost"]) is not int
            or plan["attempt_cost"] != 1
            or plan["accounting"] != "existing_remote_shared_ledger_no_reset"
            or plan["runner_sha256"] != self.runtime_sha
            or plan["ledger_ref"] != self.accounting.LEDGER_REF
            or any(plan[key] != self.registration[key] for key in BINDINGS)
        ):
            raise ValueError("native_gate_plan_binding")
        root, binding, user, uid = self.confirmation.domain(self.profile, self.anchor)
        if root != self.root or plan["resource_domain_sha256"] != binding["resource_domain_sha256"]:
            raise ValueError("native_gate_resource_binding")
        request = plan["request"]
        if set(request) != set(
            ("schema_version", "design_id", "analysis_id", "values", "result_reservation_bytes")
        ):
            raise ValueError("native_gate_request_shape")
        if type(request["schema_version"]) is not int or request["schema_version"] != 1:
            raise ValueError("native_gate_request_version")
        for key in ("design_id", "analysis_id"):
            if not self.confirmation.matches(r"^[a-z][a-z0-9-]{0,63}$", request[key]):
                raise ValueError("native_gate_request_identity")
        amount = request["result_reservation_bytes"]
        if (
            not self.confirmation.integer(amount)
            or not 1 <= amount <= self.profile["limits"]["result_reserved_bytes"]
        ):
            raise ValueError("native_gate_reservation_bound")
        route = self.route(plan)
        declared = route["variables"]
        supplied = request["values"]
        if not isinstance(supplied, list) or len(supplied) > 32 or len(declared) != len(supplied):
            raise ValueError("native_gate_explicit_inventory")
        names = [value["logical_id"] for value in supplied]
        if names != sorted(set(names)) or set(names) != set(v["logical_id"] for v in declared):
            raise ValueError("native_gate_explicit_inventory")
        for value in supplied:
            if set(value) != set(("logical_id", "value", "unit")):
                raise ValueError("native_gate_value_shape")
            variable = next(v for v in declared if v["logical_id"] == value["logical_id"])
            number = value["value"]
            if (
                not self.confirmation.matches(r"^-?(0|[1-9][0-9]{0,63})(\.[0-9]{1,63})?$", number)
                or len(number) > 48
            ):
                raise ValueError("native_gate_scalar")
            scalar = Decimal(number)
            if abs(scalar.adjusted()) > 30 or abs(scalar.as_tuple().exponent) > 40:
                raise ValueError("native_gate_scalar_bound")
            if value["unit"] != variable["unit"] or variable["mutation_policy"] == "read_only":
                raise ValueError("native_gate_registered_numeric_region")
            if variable["value_type"] == "integer" and scalar != scalar.to_integral_value():
                raise ValueError("native_gate_registered_integer")
            if variable["mutation_policy"] == "fixed":
                if number != variable["fixed_value"]:
                    raise ValueError("native_gate_registered_fixed_value")
            elif (
                variable["range_status"] != "qualified"
                or variable["minimum"] is None
                or variable["maximum"] is None
                or not Decimal(variable["minimum"]) <= scalar <= Decimal(variable["maximum"])
            ):
                raise ValueError("native_gate_registered_numeric_region")
            elif variable["step_policy"] == "grid":
                with localcontext() as precision:
                    precision.prec = 128
                    if (scalar - Decimal(variable["minimum"])) % Decimal(variable["step"]) != 0:
                        raise ValueError("native_gate_registered_grid")
        return binding, route

    def read(self, plan):
        binding, route = self.identity(plan)
        record, sha = self.confirmation.inspect(
            self.profile, plan["grant_sha256"], self.anchor, False
        )
        self.match_record(plan, record["grant"])
        return record

    def match_record(self, plan, grant):
        if any(
            grant[key] != plan[key]
            for key in ("resource_domain_sha256", "runner_sha256", "ledger_ref") + BINDINGS
        ):
            raise ValueError("native_gate_confirmed_binding")
        if (
            plan["request"]["design_id"] not in grant["design_ids"]
            or plan["analysis"] not in grant["analyses"]
        ):
            raise ValueError("native_gate_confirmed_scope")
        regions = [
            r for r in grant["numeric_regions"] if r["design_id"] == plan["request"]["design_id"]
        ]
        values = plan["request"]["values"]
        if set(r["logical_id"] for r in regions) != set(v["logical_id"] for v in values):
            raise ValueError("native_gate_confirmed_inventory")
        for value in values:
            region = next(r for r in regions if r["logical_id"] == value["logical_id"])
            if region["unit"] != value["unit"] or not Decimal(region["minimum"]) <= Decimal(
                value["value"]
            ) <= Decimal(region["maximum"]):
                raise ValueError("native_gate_confirmed_numeric_region")

    def occupancy(self):
        # Reuse the existing descriptor-pinned read-only tree scanner. No raw
        # paths/content are returned. Partial coverage cannot authorize spending.
        io = self.storage.PosixIO()
        parent = io.root(self.root)
        try:
            budget = [0]
            logical, allocated = 0, 0
            for name in (self.accounting.JOBS, "sim-mcp-v2-jobs"):
                size, blocks, fingerprint = self.storage.tree(io, parent, name, budget)
                logical += size
                allocated += blocks
            return logical, allocated
        finally:
            os.close(parent)

    def check(self, session, plan, action):
        if type(session) is not self.accounting.ReservationSession or session.root != self.root:
            raise ValueError("native_gate_owned_session")
        session.check()
        if self.activation is not None:
            self.activation()
        binding, route = self.identity(plan)
        record, confirmation_sha = self.confirmation.inspect(
            self.profile, plan["grant_sha256"], self.anchor, True
        )
        grant = record["grant"]
        self.match_record(plan, grant)
        if action not in ("authorize", "submit", "cancel_pending"):
            raise ValueError("native_gate_fixed_action")
        if action != "authorize" and action not in grant["actions"]:
            raise ValueError("native_gate_action_denied")
        for key, expected in (
            ("source_cell", "source_tree_sha256"),
            ("source_state", "ade_state_tree_sha256"),
        ):
            observed_source = self.copying.snapshot(route[key])
            if observed_source["tree_sha256"] != route["ade"][expected]:
                raise ValueError("native_gate_source_registration_drift")
        for model in route["ade"]["model_includes"]:
            if self.probe.digest_file(model["path"]) != model["file_sha256"]:
                raise ValueError("native_gate_model_registration_drift")
        observation = self.probe.observe(
            self.profile,
            self.registration["environment_sha256"],
            self.probe_sha,
            os.urandom(16).hex()
            if hasattr(bytes, "hex")
            else __import__("binascii").hexlify(os.urandom(16)).decode("ascii"),
        )
        floor = max(
            self.profile["limits"]["disk_floor_bytes"],
            (observation["total_bytes"] * self.profile["limits"]["disk_floor_percent"] + 99) // 100,
        )
        reservation = dict(binding)
        reservation.update(
            {
                "runner_sha256": plan["runner_sha256"],
                "grant_sha256": plan["grant_sha256"],
                "plan_sha256": self.accounting.digest(self.accounting.canonical(plan)),
                "execution_input_sha256": self.accounting.digest(
                    self.accounting.canonical(
                        {
                            "route": route,
                            "values": plan["request"]["values"],
                        }
                    )
                ),
                "expires_at": grant["valid_until_unix"],
                "max_attempts": grant["attempt_limit"],
                "max_reserved_bytes": grant["result_reserved_bytes_limit"],
                "reserve_bytes": plan["request"]["result_reservation_bytes"],
                "disk_floor_bytes": floor,
            }
        )
        self.accounting.check_binding(self.root, reservation)
        counter, records = session.observe(reservation)
        used = [
            intent["binding"]
            for intent, receipt in records
            if intent["binding"]["grant_sha256"] == plan["grant_sha256"]
        ]
        logical, allocated = self.occupancy()
        accounting_observation = {
            "resource_domain_sha256": plan["resource_domain_sha256"],
            "ledger_ref": plan["ledger_ref"],
            "runner_sha256": plan["runner_sha256"],
            "grant_sha256": plan["grant_sha256"],
            "cumulative_attempts": counter["count"],
            "cumulative_reserved_bytes": counter["result_reserved_bytes"],
            "grant_attempts": len(used),
            "grant_reserved_bytes": sum(v["reserve_bytes"] for v in used),
            "attempt_ceiling": self.profile["limits"]["spectre_attempts"],
            "result_ceiling_bytes": self.profile["limits"]["result_reserved_bytes"],
            "in_flight_reserved_bytes": sum(
                intent["binding"]["reserve_bytes"] for intent, receipt in records
            ),
            "logical_bytes": logical,
            "allocated_bytes": allocated,
            "filesystem_free_bytes": observation["free_bytes"],
            "filesystem_total_bytes": observation["total_bytes"],
        }
        # Cancellation requires current consent/trust but need not spend capacity.
        if action == "submit":
            if (
                accounting_observation["grant_attempts"] + 1 > grant["attempt_limit"]
                or accounting_observation["grant_reserved_bytes"] + reservation["reserve_bytes"]
                > grant["result_reserved_bytes_limit"]
                or counter["count"] + 1 > accounting_observation["attempt_ceiling"]
                or counter["result_reserved_bytes"] + reservation["reserve_bytes"]
                > accounting_observation["result_ceiling_bytes"]
                or observation["free_bytes"]
                < floor
                + accounting_observation["in_flight_reserved_bytes"]
                + reservation["reserve_bytes"]
            ):
                raise ValueError("native_gate_capacity_or_disk_floor")
        # Recheck live consent after version wrappers/scan, directly before write.
        self.confirmation.inspect(self.profile, plan["grant_sha256"], self.anchor, True)
        session.check()
        if self.activation is not None:
            self.activation()
        return reservation, accounting_observation
