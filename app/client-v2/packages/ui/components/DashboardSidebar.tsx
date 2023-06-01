import { Fade, List, ListItem, ListItemButton, ListItemIcon, Typography } from "@mui/material";
import { useState } from "react";

import { makeStyles } from "../lib/ThemeProvider";

export type DashboardSidebarProps = {
  items: { link: string; icon: () => JSX.Element; placeholder: string }[];
  width: number;
  extended_width: number;
};

export function DashboardSidebar(props: DashboardSidebarProps) {
  const { items } = props;
  const { classes, cx } = useStyles(props)();

  const [hover, setHover] = useState(false);

  const handleHover = () => {
    setHover((currHover) => !currHover);
  };

  return (
    <nav className={cx(classes.root)} onMouseEnter={handleHover} onMouseLeave={handleHover}>
      <List sx={{ "& .MuiListItem-root": { paddingLeft: 0, paddingRight: 0 } }}>
        {items?.map(({ link, icon, placeholder }) => (
          <ListItem disablePadding key={link}>
            <ListItemButton>
              <ListItemIcon>{icon()}</ListItemIcon>
              {hover ? (
                <Fade in={true}>
                  <Typography fontSize="14px" color="dark.greyVariant4" marginLeft={-1.5}>
                    {placeholder}
                  </Typography>
                </Fade>
              ) : (
                <></>
              )}
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </nav>
  );
}

const useStyles = (props: DashboardSidebarProps) =>
  makeStyles({ name: { DashboardSidebar } })((theme) => ({
    root: {
      backgroundColor: theme.colors.palette.light.light,
      cursor: "pointer",
      width: props.width,
      left: 0,
      top: 0,
      bottom: 0,
      position: "fixed",
      transition: "width 0.4s ease",
      display: "flex",
      flexDirection: "column",
      "&:hover": {
        width: props.extended_width,
      },
    },
  }));
