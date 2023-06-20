// Copyright (c) 2020 GitHub user u/garronej

/* eslint-disable @typescript-eslint/ban-types */
import SvgIcon from "@mui/material/SvgIcon";
import { memo, forwardRef } from "react";
import type { ForwardedRef, MouseEventHandler, ElementType } from "react";
import type { Equals } from "tsafe";
import { assert } from "tsafe/assert";

import { makeStyles } from "../../lib/ThemeProvider";
import type { Theme } from "../../lib/ThemeProvider";
import type { IconSizeName } from "../../lib/icon";
import { changeColorOpacity } from "../../tools/changeColorOpacity";

/**
 * Size:
 *
 * If you want to change the size of the icon you can set the font
 * size manually with css using one of the typography
 * fontSize of the root in px.
 *
 * If you place it inside a <Text> element you can define it's size proportional
 * to the font-height:
 * {
 *     "fontHeight": "inherit",
 *     ...(()=>{
 *         const factor = 1.3;
 *         return { "width": `${factor}em`, "height": `${factor}em` }
 *     })()
 * }
 *
 * Color:
 *
 * By default icons inherit the color.
 * If you want to change the color you can
 * simply set the style "color".
 *
 */
export type IconProps<IconId extends string = string> = {
  iconId: IconId;
  className?: string;
  wrapped?: "circle" | "square";
  /** default default */
  size?: IconSizeName;
  bgVariant?: "focus" | "secondary" | "gray" | "gray2";
  bgOpacity?: number;
  iconVariant?: "white" | "secondary" | "focus" | "gray";
  onClick?: MouseEventHandler<SVGSVGElement>;
};

export type MuiIconLike = (props: {
  ref: ForwardedRef<SVGSVGElement>;
  className: string;
  onClick?: MouseEventHandler<SVGSVGElement>;
}) => JSX.Element;

export type SvgComponentLike = ElementType;

// function blendHexColorWithOpacity(hexColor: string, opacity: number) {
//   // Remove the '#' character from the hex color
//   const normalizedHexColor = hexColor.replace("#", "");

//   // Convert the opacity to its hexadecimal equivalent
//   const opacityHex = Math.round(opacity * 255)
//     .toString(16)
//     .padStart(2, "0");

//   // Combine the opacity hex value with the original hex color
//   const blendedHexColor = `#${normalizedHexColor}${opacityHex}`;
//   return blendedHexColor;
// }

function isMuiIcon(Component: MuiIconLike | SvgComponentLike): Component is MuiIconLike {
  return "type" in (Component as MuiIconLike);
}

function getBgColor(key: "focus" | "secondary" | "gray" | "white" | "gray2", theme: Theme): string {
  switch (key) {
    case "focus":
      return theme.colors.palette.focus.main;
    case "secondary":
      return theme.colors.palette.light.main;
    case "gray":
      return theme.colors.palette.light.greyVariant4;
    case "gray2":
      return theme.colors.palette.light.greyVariant2;
    default:
      return "light";
  }
}

export function createIcon<IconId extends string>(componentByIconId: {
  readonly [iconId in IconId]: MuiIconLike | SvgComponentLike;
}) {
  const useStyles = makeStyles<{
    size: IconSizeName;
    wrapped: "circle" | "square" | undefined;
    bgVariant: "focus" | "secondary" | "gray" | "gray2";
    iconVariant: "white" | "secondary" | "focus" | "gray";
    bgOpacity: number;
  }>()((theme, { size, wrapped, bgVariant, iconVariant, bgOpacity }) => ({
    root: {
      color: getBgColor(iconVariant, theme),
      verticalAlign: "top",
      fontSize: theme.iconSizesInPxByName[size],
      width: "1em",
      position: "relative",
    },
    iconWrapper: {
      // backgroundColor: wrapped ? `${theme.colors.palette.focus.main}14` : "",
      // width: 'fit-content',
      // height: 'fit-content',
      // borderRadius: wrapped === "circle" ? "50%" : 4,
      padding: wrapped ? "4px" : "",
      display: "flex",
      alignItems: "center",
      width: "fit-content",
      height: "fit-content",
      borderRadius: wrapped === "circle" ? "50%" : 4,
      backgroundColor: wrapped
        ? changeColorOpacity({ color: getBgColor(bgVariant, theme), opacity: bgOpacity })
        : "", //theme.colors.palette.focus.main
    },
  }));

  const Icon = memo(
    forwardRef<SVGSVGElement, IconProps<IconId>>((props, ref) => {
      const {
        iconId,
        wrapped,
        bgOpacity = 0.08,
        className,
        size = "default",
        onClick,
        bgVariant = "focus",
        iconVariant = "focus",
        ...rest
      } = props;

      //For the forwarding, rest should be empty (typewise),
      assert<Equals<typeof rest, {}>>();

      const { classes, cx } = useStyles({ size, wrapped, bgVariant, iconVariant, bgOpacity });

      const Component: MuiIconLike | SvgComponentLike = componentByIconId[iconId];

      return isMuiIcon(Component) ? (
        <div className={classes.iconWrapper}>
          <Component ref={ref} className={cx(classes.root, className)} onClick={onClick} {...rest} />
        </div>
      ) : (
        <div className={classes.iconWrapper}>
          <SvgIcon
            ref={ref}
            onClick={onClick}
            className={cx(classes.root, className)}
            component={Component}
            {...rest}
          />
        </div>
      );
    })
  );

  return { Icon };
}

/*
NOTES:
https://github.com/mui-org/material-ui/blob/e724d98eba018e55e1a684236a2037e24bcf050c/packages/material-ui/src/styles/createTypography.js#L45
https://github.com/mui-org/material-ui/blob/53a1655143aa4ec36c29a6063ccdf89c48a74bfd/packages/material-ui/src/Icon/Icon.js#L12
*/
