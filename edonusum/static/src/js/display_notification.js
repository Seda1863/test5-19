odoo.define('edonusum.display_notification', function (require) {
    'use strict';

    var core = require('web.core');
    var Notification = require('web.Notification');

    // Client action ile bildirimi göstermek için
    core.action_registry.add('display_notification', function (action) {
        var params = action.params;
        
        var message = params.message || '';
        var title = params.title || '';
        var type = params.type || 'info';  // Varsayılan tip 'info'
        var sticky = params.sticky || false;

        var notification = new Notification(message, {
            title: title,
            type: type,
            sticky: sticky,
        });

        notification.insertAfter($('.o_content'));  // Bildirimi o_content elementinin sonrasında göster
    });
});
