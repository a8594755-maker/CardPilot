import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { LegalStandalonePage, getLegalRoute } from "./legal-pages";
import "./styles.css";

const legalRoute = typeof window !== "undefined" ? getLegalRoute(window.location.pathname) : null;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {legalRoute ? (
      <LegalStandalonePage route={legalRoute} />
    ) : (
      <BrowserRouter>
        <App />
      </BrowserRouter>
    )}
  </React.StrictMode>
);
