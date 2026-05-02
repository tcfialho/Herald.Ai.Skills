---
version: alpha
name: TBD Project Design System
description: TBD visual identity documented after the static prototype is accepted.
colors:
  primary: "#1A1C1E"
  on-primary: "#FFFFFF"
  secondary: "#6C7278"
  tertiary: "#B8422E"
  neutral: "#F7F5F2"
  surface: "#FFFFFF"
  on-surface: "#1A1C1E"
  error: "#B42318"
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: 0
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0
rounded:
  none: 0px
  sm: 4px
  md: 8px
  lg: 12px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    padding: 12px
  button-primary-hover:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.on-primary}"
  input-default:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.sm}"
    padding: 12px
---

# Design System

## Overview

TBD: Describe the accepted prototype direction, product personality, target audience, and visual intent.

## Colors

The palette must match the accepted static prototype.

- **Primary (#1A1C1E):** Main actions, active states, and high-emphasis UI.
- **On-primary (#FFFFFF):** Text and icons placed on primary surfaces.
- **Secondary (#6C7278):** Supporting UI, borders, captions, and metadata.
- **Tertiary (#B8422E):** Accent color for selective emphasis.
- **Neutral (#F7F5F2):** Soft page foundation or quiet container tone.
- **Surface (#FFFFFF):** Main content surfaces.
- **On-surface (#1A1C1E):** Primary text on surfaces.
- **Error (#B42318):** Validation errors and destructive states.

## Typography

- **Headlines:** Inter bold for clear hierarchy and page titles.
- **Body:** Inter regular at 16px for readable product content.
- **Labels:** Inter semi-bold at 12px for controls, captions, and metadata.

## Layout

TBD: Describe the accepted prototype grid, containment, responsive behavior, and spacing strategy.

## Elevation & Depth

TBD: Describe how the accepted prototype creates hierarchy: borders, shadows, tonal layers, or elevation.

## Shapes

TBD: Describe corner radius, edge treatment, and shape language used in the accepted prototype.

## Components

- **Buttons:** Primary, secondary, hover, disabled, and loading behavior.
- **Inputs:** Default, focused, error, disabled, and helper text behavior.
- **Cards:** Container treatment, border/elevation, spacing, and density.
- **Navigation:** Active, hover, collapsed, and mobile states.

## Do's and Don'ts

- Do keep future UI consistent with these tokens.
- Do update this file when accepted prototype direction changes.
- Don't introduce one-off styling without updating this file.
- Don't add UI behavior that is not represented in `nexus/spec.md`.
