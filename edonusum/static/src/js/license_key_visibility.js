/** filepath: c:\Users\ABAS\Documents\minddx-odoo\Odoo\addons\edonusum\static\src\js\license_key_visibility.js **/
odoo.define('edonusum.license_key_visibility', function (require) {
    "use strict";

    const { Component } = owl;
    const { useState } = owl.hooks;

    function togglePasswordVisibility(ev) {
        const inputField = document.querySelector('input[name="edonusum_license_key"]');
        if (inputField) {
            if (inputField.type === "password") {
                inputField.type = "text";
                ev.target.innerText = "Gizle";
            } else {
                inputField.type = "password";
                ev.target.innerText = "Göster";
            }
        }
    }

    return {
        togglePasswordVisibility: togglePasswordVisibility,
    };
});