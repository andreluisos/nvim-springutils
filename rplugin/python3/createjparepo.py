from pathlib import Path

from pynvim.api.nvim import Nvim
from tree_sitter import Node

from pathutil import PathUtil
from tsutil import TreesitterUtil
from messaging import Messaging
from constants.java_types import JAVA_TYPES


class CreateJpaRepository:
    def __init__(
        self,
        nvim: Nvim,
        tsutil: TreesitterUtil,
        pathutil: PathUtil,
        messaging: Messaging,
    ):
        self.nvim = nvim
        self.tsutil = tsutil
        self.pathutil = pathutil
        self.messaging = messaging
        self.java_types = JAVA_TYPES
        self.class_annotation_query = """
        (class_declaration
            (modifiers
                (marker_annotation
                name: (identifier) @annotation_name
                )
            )
        )
        """
        self.field_declaration_query = """
        (field_declaration
            (modifiers
                (annotation
                name: (identifier) @annotation_name
                )
            )
        )
        """
        self.id_field_annotation_query = """
        (modifiers
            (marker_annotation
                name: (identifier) @annotation_name
            )
        )
        """
        self.superclass_query = """
        (superclass
            (type_identifier) @superclass_name
         )
        """
        self.class_name_query = """
        (class_declaration
            name: (identifier) @class_name
            )
        """

    def generate_jpa_repository_template(
        self, class_name: str, package_path: str, id_type: str, debugger: bool = False
    ) -> str:
        id_type_import_path = self.tsutil.get_field_type_import_path(id_type, debugger)
        boiler_plate = (
            f"package {package_path};\n\n"
            f"import org.springframework.data.jpa.repository.JpaRepository;\n\n"
        )
        if id_type_import_path:
            boiler_plate += f"import {id_type_import_path};\n\n"
        boiler_plate += f"public interface {class_name}Repository extends JpaRepository<{class_name}, {id_type}> {{}}"
        if debugger:
            self.messaging.log(f"Boiler plate: {boiler_plate}", "debug")
        return boiler_plate

    def check_if_jpa_entity(self, buffer_node: Node, debugger: bool = False) -> bool:
        results = self.tsutil.query_node(
            buffer_node, self.class_annotation_query, debugger=debugger
        )
        buffer_is_entity = self.tsutil.query_results_has_term(
            results, "Entity", debugger=debugger
        )
        if not buffer_is_entity:
            return False
        return True

    def check_if_id_field_exists(
        self, buffer_node: Node, debugger: bool = False
    ) -> bool:
        results = self.tsutil.query_node(
            buffer_node, self.id_field_annotation_query, debugger=debugger
        )
        id_annotation_found = self.tsutil.query_results_has_term(
            results, "Id", debugger=debugger
        )
        if not id_annotation_found:
            return False
        return True

    def get_superclass_query_node(
        self, buffer_node: Node, debugger: bool = False
    ) -> Node | None:
        results = self.tsutil.query_node(
            buffer_node, self.superclass_query, debugger=debugger
        )
        if len(results) == 0:
            return None
        return results[0][0]

    def find_superclass_file_node(
        self, root_path: Path, superclass_name: str, debugger: bool = False
    ) -> Node | None:
        for p in root_path.rglob("*.java"):
            _node = self.tsutil.get_node_from_path(p, debugger=debugger)
            _results = self.tsutil.query_node(
                _node, self.class_name_query, debugger=debugger
            )
            if len(_results) == 0:
                continue
            class_name = self.tsutil.get_node_text(_results[0][0], debugger=debugger)
            if class_name == superclass_name:
                return _node
        return None

    def find_id_field_type(
        self, buffer_node: Node, debugger: bool = False
    ) -> str | None:
        child_node = buffer_node.children
        for child in child_node:
            if child.type != "class_declaration":
                self.find_id_field_type(child)
            else:
                for c1 in child.children:
                    if c1.type == "class_body":
                        for c2 in c1.children:
                            if c2.type == "field_declaration":
                                id_field_found = False
                                for c3 in c2.children:
                                    # c3 = modifiers, type_identifer and variable_declarator
                                    if c3.type == "modifiers":
                                        for c4 in c3.children:
                                            if c4.type == "marker_annotation":
                                                for c5 in c4.children:
                                                    if c5.type == "identifier":
                                                        if (
                                                            self.tsutil.get_node_text(
                                                                c5
                                                            )
                                                            == "Id"
                                                        ):
                                                            id_field_found = True
                                    if id_field_found and c3.type == "type_identifier":
                                        id_field_type = self.tsutil.get_node_text(c3)
                                        if debugger:
                                            self.messaging.log(
                                                f"Id field type: {id_field_type}",
                                                "debug",
                                            )
                                        return self.tsutil.get_node_text(c3)
        self.messaging.log("Id field type not found", "debug")
        return None

    def create_jpa_repository_file(
        self,
        buffer_path: Path,
        class_name: str,
        boiler_plate: str,
        debugger: bool = False,
    ) -> None:
        file_path = buffer_path.parent.joinpath(f"{class_name}Repository.java")
        if debugger:
            self.messaging.log(f"Class name: {class_name}", "debug")
            self.messaging.log(f"JPA repository path: {file_path}", "debug")
            self.messaging.log(f"Boiler plate: {boiler_plate}", "debug")
        if not file_path.exists():
            with open(file_path, "w") as java_file:
                java_file.write(boiler_plate)
            if file_path.exists():
                if debugger:
                    self.messaging.log(
                        "Successfuly created JPA repository file.", "debug"
                    )
                self.nvim.command(f"edit {file_path}")
                # TODO: make sure jdtls is in plugin dependencies.
                self.nvim.command("lua require('jdtls').organize_imports()")
                return
        self.messaging.log(
            "Unable to create JPA repository file.", "error", send_msg=True
        )
        return

    def create_jpa_entity_for_current_buffer(
        self, root_path: Path, debugger: bool = False
    ) -> None:
        buffer_path = Path(self.nvim.current.buffer.name)
        node = self.tsutil.get_node_from_path(buffer_path, debugger=debugger)
        class_name = self.tsutil.get_node_class_name(node, debugger=debugger)
        package_path = self.pathutil.get_buffer_package_path(
            buffer_path, debugger=debugger
        )
        if class_name is None:
            self.messaging.log(
                "Couldn't find the class name for this buffer.", "error", send_msg=True
            )
            return
        if not self.check_if_jpa_entity(node):
            self.messaging.log(
                "Current buffer isn't a JPA entity.", "error", send_msg=True
            )
            return
        if not self.check_if_id_field_exists(node, debugger=debugger):
            superclass_name_node = self.get_superclass_query_node(
                node, debugger=debugger
            )
            if not superclass_name_node:
                self.messaging.log(
                    "No Id found for this entity and no superclass to look for it.",
                    "error",
                    send_msg=True,
                )
                return
            superclass_name = self.tsutil.get_node_text(
                superclass_name_node, debugger=debugger
            )
            superclass_node = self.find_superclass_file_node(
                root_path, superclass_name, debugger
            )
            if superclass_node is None:
                self.messaging.log(
                    "Unable to locate the superclass buffer.", "error", send_msg=True
                )
                return
            if not self.check_if_id_field_exists(superclass_node, debugger=debugger):
                # TODO: Keep checking for superclasses?
                self.messaging.log(
                    "Unable to find the Id field on the superclass.",
                    "error",
                    send_msg=True,
                )
                return
            id_type = self.find_id_field_type(superclass_node, debugger=debugger)
            if id_type is None:
                self.messaging.log(
                    "Unable to find get the Id field type on the superclass.",
                    "error",
                    send_msg=True,
                )
                return
            boiler_plate = self.generate_jpa_repository_template(
                class_name=class_name,
                package_path=package_path,
                id_type=id_type,
                debugger=debugger,
            )
            self.create_jpa_repository_file(
                buffer_path=buffer_path,
                class_name=class_name,
                boiler_plate=boiler_plate,
                debugger=debugger,
            )
