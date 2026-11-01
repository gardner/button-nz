"""The Dwelling's finishes in the trusted render: the host's colour over a CC0
texture from ``textures/``, laid on the baked mesh's UVs (metres, from
``surface_math``). Runs in Blender's Python, imported by ``design_measure``.

A finish is the product's colour multiplied over a greyscale detail map, with
the texture's normal map and the finish's roughness. Its scale and turn are a
Mapping node, which glTF exports as ``KHR_texture_transform``.
"""

import json
import math
import os
from typing import Any

import bpy  # pyright: ignore[reportMissingImports]

b: Any = bpy  # no type stubs inside Blender
TEXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "textures")


def textures() -> dict[str, Any]:
    """The texture sets, by name, as ``textures/textures.json`` describes them."""
    with open(os.path.join(TEXTURES, "textures.json"), encoding="utf-8") as f:
        sets: dict[str, Any] = json.load(f)["sets"]
    return sets


def material(name: str, finish: dict[str, Any]) -> Any:
    """A material for ``finish``: its ``rgba`` (linear) over its ``texture``."""
    texture = finish["texture"]
    spec = textures()[texture]  # the host names only committed sets
    rgba = tuple(finish["rgba"])
    material = b.data.materials.new(name)
    material.diffuse_color = rgba
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = spec["roughness"]
    mapping = _mapping(nodes, links, spec)
    detail = _image(nodes, f"{texture}_detail.jpg", "sRGB")
    normal = _image(nodes, f"{texture}_normal.jpg", "Non-Color")
    for image in (detail, normal):
        links.new(mapping.outputs["Vector"], image.inputs["Vector"])
    tint = nodes.new("ShaderNodeMix")
    tint.data_type, tint.blend_type = "RGBA", "MULTIPLY"
    tint.inputs["Factor"].default_value = 1.0
    links.new(detail.outputs["Color"], _colour(tint.inputs, "A"))
    _colour(tint.inputs, "B").default_value = rgba
    links.new(_colour(tint.outputs, "Result"), bsdf.inputs["Base Color"])
    normal_map = nodes.new("ShaderNodeNormalMap")
    links.new(normal.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def _mapping(nodes: Any, links: Any, spec: dict[str, Any]) -> Any:
    """UVs in metres to tiles of ``tile_m``, turned so boards run level if asked."""
    coordinates = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    scale = 1.0 / spec["tile_m"]
    mapping.inputs["Scale"].default_value = (scale, scale, 1.0)
    if spec["boards_across"]:  # the photographs' boards run up the image
        mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.pi / 2)
    links.new(coordinates.outputs["UV"], mapping.inputs["Vector"])
    return mapping


def _image(nodes: Any, filename: str, colour_space: str) -> Any:
    node = nodes.new("ShaderNodeTexImage")
    node.image = b.data.images.load(os.path.join(TEXTURES, filename), check_existing=True)
    node.image.colorspace_settings.name = colour_space
    return node


def _colour(sockets: Any, name: str) -> Any:
    """The colour socket called ``name`` (a Mix node has one per data type)."""
    return next(s for s in sockets if s.name == name and s.type == "RGBA")
