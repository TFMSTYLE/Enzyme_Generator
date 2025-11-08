# Enzyme Generator

![enzyme-thumb](https://github.com/user-attachments/assets/0fef119e-c1be-4a79-a086-a85243001955)

**Author:** The French Monkey (TFMSTYLE)  
**Version:** 1.0.0  

---

## Overview

The Enzyme Generator is a procedural modeling system that builds complex enzyme-inspired 3D structures.  
Each enzyme class — such as Hydrolase, Transferase, or Ligase — generates unique structural patterns based on biological folding concepts.  
The system uses parametric helix, sheet, and loop primitives to assemble detailed, stylized biomolecular shapes suitable for scientific visualization, concept design, or abstract modeling.

---

## Parameters

### Live Update
When enabled, the enzyme regenerates automatically after any parameter change.  
Useful for interactive adjustments, though it may slow performance with high detail levels.

---

### Class
Defines the enzyme family, determining the characteristic folding pattern and overall structural arrangement.  
Available types include:  
- **Hydrolase** – Compact and spherical, with alternating helices and sheets.  
- **Oxidoreductase** – Dense helical packing with complex loop connections.  
- **Transferase** – Layered sheets bridged by structured helices.  
- **Lyase** – Elongated structures with central backbones.  
- **Isomerase** – Symmetrical twisted configurations.  
- **Ligase** – Parallel domains with alternating helices and sheets.

---

### Size
Scales the enzyme’s overall dimensions.  
Affects the span of domains, helices, and loops.

---

### Compactness
Controls how tightly folded the enzyme is.  
Lower values create more open structures, while higher values produce denser, compact forms.

---

### Domains
Sets the number of domain regions composing the enzyme.  
Each domain contributes a localized fold pattern to the global shape.

---

### Seed
Random seed for structural variation.  
Changing this produces a new enzyme shape with the same base parameters.

---

### Helices
Number of helices distributed throughout the structure.  
Higher values increase complexity and density.

---

### Helix Radius
Controls the base radius of each helix segment.  
Affects the perceived thickness and scale of the helical regions.

---

### Helix Pitch
Defines the vertical distance per turn of each helix.  
Higher values create stretched helices; lower values make them more compact.

---

### Helix Turns
Sets the number of complete rotations per helix strand.  
Influences the length and proportion of individual helices.

---

### Helix Elongation
Stretches the helix profile along its axis.  
Useful for emphasizing directionality or elongating folds.

---

### Tube Radius
Determines the cross-sectional thickness of tube-based geometry (helices and loops).  
Affects strand diameter and smoothness.

---

### Ribbon Width
Specifies the width of ribbon-like sheet regions.  
Wider values produce broader β-sheet surfaces.

---

### Curve Resolution
Sets the number of control points used per generated curve.  
Higher resolution increases smoothness at the cost of performance.

---

### Bevel Resolution
Controls the smoothness of the cross-section profile used in beveling.  
Higher values yield rounder, more refined geometry.

---

### Sheets
Number of sheet regions generated within the enzyme.  
These represent flattened β-structures or extended planar folds.

---

### Sheet Thickness
Defines the extrusion depth of sheet profiles.  
Adjust to control the perceived thinness or solidity of the ribbon regions.

---

### Sheet Twist
Adds a twisting factor along sheet surfaces.  
Higher values produce more dynamic, wave-like shapes.

---

### Loop Slack
Determines the curvature and looseness of the connecting loops between domains.  
Higher values create longer, more flexible connections.

---

### Loop Radius
Specifies the tube thickness used for loops.  
Affects the prominence of interconnecting bridges.

---

## Operators

### Generate Enzyme
Creates a new enzyme master object and generates its hierarchical structure.  
Each enzyme includes an Empty parent, a mesh container, and all child geometries organized within.

---

### Update Enzyme
Rebuilds the selected enzyme with the current parameters.  
Retains the existing object hierarchy but replaces the geometry.

---

### Delete Selected Enzyme
Removes the selected enzyme and all associated objects from the scene.  
Also purges unused curve datablocks.

---

### Reset Settings
Restores all parameter values to their defaults.  
The Live Update state is preserved.

---

## Usage Notes

- The **Class** parameter determines the overall folding logic and structural motif.  
- **Compactness** and **Domain Count** directly influence clustering and spatial complexity.  
- Enable **Live Update** for design iteration, then disable it for heavy scenes.  
- Each enzyme is color-coded according to its class type for easy identification.  
- For best results, apply subdivision and smoothing modifiers to the generated meshes for final rendering.  
- Generated materials use Blender’s Principled BSDF shader with subtle subsurface scattering for realistic shading.
