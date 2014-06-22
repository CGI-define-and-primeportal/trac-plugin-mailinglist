// -*- mode: Javascript; indent-tabs-mode: nil; -*-

jQuery(function($){
    $('.moreinfo').click(function(e) {
      $("i", this).toggleClass("icon-resize-full icon-resize-small");
      $(this).closest('tr').next().toggleClass('hidden');
      $("span", this).text($("span", this).text() == "More info" ? "Less Info" : "More info");
      if($(this).hasClass("last-row")) $(this).closest("tr").toggleClass("last-row");
    });
    $('a.subscribe').click(function(e) {
        $(this).closest('form').submit();
        return false;
    })
    $(".viewinfo").click(function(e){
      e.preventDefault();
    	var parent = $(this).closest('div').parent();
    	parent.next('.information').toggleClass('hidden');
    	
    });
    $(".morebody").each(function(index){
      if ($(this).closest('div.conversation').find('.quoted').length == 0) {
        $(this).addClass("color-muted");
      } else { 
        var n = $(this).closest('div.conversation').find('.quoted').data('quotedmessages');
        if ($.isNumeric(n)) { // just in case somehow data was interfered with
          $(this).text("Show " + n + " Quoted");
        };
      };
    });
    $(".morebody").click(function(e){
      e.preventDefault();
      $(this).closest('div.conversation').find('.quoted').toggleClass('hidden');
    });
    $("#subscribe-link").click(function(){
      $("#subscribe-form").submit()
    });

})
